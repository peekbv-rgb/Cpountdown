from __future__ import annotations

import base64
import os
import shutil
import time
from pathlib import Path
from typing import Callable

import requests

from public_tunnel import TemporaryPublicVideo


ProgressFn = Callable[[str], None]


class FitnessKlingClient:
    """Small direct Kling Open Platform client for Motion Control.

    Kling Motion Control requires video_url to be a real retrievable HTTPS URL. Local motion
    files are therefore exposed only temporarily through a Cloudflare Quick Tunnel while the
    Kling task runs. The character image is sent as base64.
    """

    DEFAULT_BASE_URL = "https://api.klingai.com"
    DEFAULT_CREATE_PATH = "/v1/videos/motion-control"

    def __init__(self, api_key: str, poll_interval: float = 4.0):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("Kling API key ontbreekt")

        self.api_key = api_key
        self.poll_interval = max(1.0, float(poll_interval))
        self.base_url = os.getenv("KLING_API_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")
        self.create_path = os.getenv("KLING_MOTION_PATH", self.DEFAULT_CREATE_PATH)
        if not self.create_path.startswith("/"):
            self.create_path = "/" + self.create_path

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    @staticmethod
    def _image_base64(path: str | Path) -> str:
        return base64.b64encode(Path(path).read_bytes()).decode("ascii")

    @staticmethod
    def _download(url: str, output_path: str | Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, stream=True, timeout=180) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                shutil.copyfileobj(response.raw, handle)
        return output_path

    @staticmethod
    def _error_message(data: dict, prefix: str, status_code: int | None = None) -> RuntimeError:
        code = data.get("code", "onbekend")
        message = (
            data.get("message")
            or data.get("msg")
            or data.get("error")
            or data.get("detail")
            or "Geen nadere omschrijving."
        )
        request_id = data.get("request_id") or data.get("requestId")
        http = f" HTTP {status_code}." if status_code else ""
        text = f"{prefix}.{http} Kling-code: {code}. Reden: {message}."
        if request_id:
            text += f" Request-ID: {request_id}."
        return RuntimeError(text)

    def _request_json(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self.session.request(
                method,
                self.base_url + path,
                timeout=90,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Geen verbinding met Kling API: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            body = response.text[:500]
            raise RuntimeError(
                f"Kling gaf geen geldige JSON terug (HTTP {response.status_code}). Antwoord: {body}"
            ) from exc

        if response.status_code >= 400:
            raise self._error_message(data, "Kling API aanvraag mislukt", response.status_code)

        code = data.get("code")
        if code not in (None, 0, "0"):
            raise self._error_message(data, "Kling API heeft de aanvraag geweigerd", response.status_code)
        return data

    @staticmethod
    def _extract_task_id(created: dict) -> str:
        data = created.get("data") or created
        return str(data.get("task_id") or data.get("taskId") or "").strip()

    @staticmethod
    def _extract_video_url(info: dict) -> str:
        data = info.get("data") or info
        result = data.get("task_result") or data.get("taskResult") or data.get("result") or {}
        videos = result.get("videos") or result.get("video") or []
        if isinstance(videos, dict):
            videos = [videos]
        if videos and isinstance(videos[0], dict):
            return videos[0].get("url") or videos[0].get("video_url") or ""
        return ""

    def generate_motion_control(
        self,
        character_image: str | Path,
        reference_video: str | Path,
        output_path: str | Path,
        prompt: str = "",
        mode: str = "std",
        character_orientation: str = "video",
        keep_original_sound: bool = False,
        progress: ProgressFn | None = None,
        timeout: float = 20 * 60,
    ) -> Path:
        character_image = Path(character_image)
        reference_video = Path(reference_video)
        if not character_image.exists():
            raise FileNotFoundError(f"Character-afbeelding ontbreekt: {character_image}")
        if not reference_video.exists():
            raise FileNotFoundError(f"Motion-video ontbreekt: {reference_video}")

        mode = mode if mode in {"std", "pro"} else "std"
        character_orientation = character_orientation if character_orientation in {"video", "image"} else "video"

        if progress:
            progress(f"Kling Motion Control voorbereiden: {reference_video.name}…")

        # Kling validates video_url as an actual downloadable URL; data: URIs are rejected
        # with code 1201. Keep a temporary HTTPS tunnel alive until Kling is done fetching
        # and processing the motion video.
        with TemporaryPublicVideo(reference_video, progress=progress) as public_video_url:
            payload = {
                "model_name": "kling-v3",
                "image_url": self._image_base64(character_image),
                "video_url": public_video_url,
                "prompt": (prompt or "")[:2500],
                "keep_original_sound": "yes" if keep_original_sound else "no",
                "character_orientation": character_orientation,
                "mode": mode,
            }

            # A brand-new trycloudflare.com hostname can be visible in public DNS a few seconds
            # before every external resolver has caught up. If Kling returns 1201 during that
            # short window, keep the same tunnel alive and retry instead of making the user start over.
            created = None
            retry_delays = (0, 8, 15, 25)
            last_error: Exception | None = None
            for attempt, delay in enumerate(retry_delays, start=1):
                if delay:
                    if progress:
                        progress(
                            f"Kling zag de nieuwe video-URL nog niet; DNS-warm-up {delay}s en opnieuw proberen "
                            f"({attempt}/{len(retry_delays)})…"
                        )
                    time.sleep(delay)

                if progress:
                    progress("Kling Motion Control-taak indienen…")

                try:
                    created = self._request_json("POST", self.create_path, json=payload)
                    break
                except RuntimeError as exc:
                    last_error = exc
                    text = str(exc).lower()
                    retryable_video_url_error = (
                        "kling-code: 1201" in text
                        or "video url is invalid" in text
                        or "video_url" in text and "invalid" in text
                    )
                    if not retryable_video_url_error or attempt == len(retry_delays):
                        raise

            if created is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("Kling Motion Control kon niet worden gestart.")

            task_id = self._extract_task_id(created)
            if not task_id:
                raise RuntimeError(f"Kling gaf geen task_id terug. Antwoord: {created}")

            started = time.monotonic()
            while True:
                if time.monotonic() - started > timeout:
                    raise TimeoutError(
                        f"Kling Motion Control time-out na {timeout / 60:.0f} minuten. Task-ID: {task_id}"
                    )

                time.sleep(self.poll_interval)
                status_payload = self._request_json("GET", f"{self.create_path}/{task_id}")
                info = status_payload.get("data") or status_payload
                status = str(
                    info.get("task_status")
                    or info.get("taskStatus")
                    or info.get("status")
                    or ""
                ).lower()

                if progress:
                    label = {
                        "submitted": "in wachtrij",
                        "pending": "in wachtrij",
                        "processing": "wordt gegenereerd",
                        "running": "wordt gegenereerd",
                        "succeed": "klaar",
                        "success": "klaar",
                        "completed": "klaar",
                        "failed": "mislukt",
                        "fail": "mislukt",
                        "error": "mislukt",
                    }.get(status, status or "status onbekend")
                    progress(f"Kling Motion Control: {label} · task {task_id[:8]}…")

                if status in {"submitted", "pending", "processing", "running", ""}:
                    continue

                if status in {"failed", "fail", "error"}:
                    reason = (
                        info.get("task_status_msg")
                        or info.get("taskStatusMsg")
                        or info.get("message")
                        or "Geen foutdetails ontvangen."
                    )
                    raise RuntimeError(
                        f"Kling Motion Control mislukt. Reden: {reason}. Task-ID: {task_id}."
                    )

                if status in {"succeed", "success", "completed"}:
                    url = self._extract_video_url(status_payload)
                    if not url:
                        raise RuntimeError(
                            f"Kling-task is klaar maar bevat geen video-URL. Task-ID: {task_id}. Antwoord: {status_payload}"
                        )
                    if progress:
                        progress("Kling-video downloaden…")
                    return self._download(url, output_path)

                raise RuntimeError(
                    f"Onbekende Kling-taskstatus '{status}'. Task-ID: {task_id}. Antwoord: {status_payload}"
                )
