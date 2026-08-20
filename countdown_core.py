from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

TOTAL_SECONDS = 62
COUNT_FROM = 60
SEGMENT_SECONDS = 10


@dataclass(frozen=True)
class Scene:
    person: str
    clothing: str
    environment: str

    def prompt(self) -> str:
        return (
            f"Photorealistic AI-generated {self.person}. {self.clothing}. "
            f"Scene: {self.environment}. Medium close-up, centered and symmetrical. "
            "The person looks intensely and continuously straight into the camera lens, "
            "confident expression, minimal head movement, natural blinking, stable face, "
            "realistic anatomy. Energetic premium fitness campaign lighting. No text, "
            "no logos, no camera movement, no cuts."
        )


LANDMARKS = [
    "Paris at blue hour, Eiffel Tower clearly visible in the background",
    "New York harbor at sunrise, Statue of Liberty clearly visible",
    "Agra at golden hour, Taj Mahal clearly visible in the background",
    "London after rain, Big Ben and Westminster clearly visible",
    "Sydney waterfront at dawn, Sydney Opera House clearly visible",
    "Rio de Janeiro at sunset, Christ the Redeemer clearly visible",
    "Rome at night, Colosseum clearly visible with tasteful architectural lighting",
]

CASTS = {
    "Dezelfde vrouw": ["the same athletic woman in her mid thirties, identical face, hair and body proportions in every scene"],
    "Dezelfde man": ["the same athletic man in his mid thirties, identical face, hair and body proportions in every scene"],
    "Wisselende vrouwen": [
        "athletic woman in her late twenties", "athletic woman in her mid thirties",
        "athletic woman in her forties", "athletic woman in her early fifties",
    ],
    "Wisselende mannen": [
        "athletic man in his late twenties", "athletic man in his mid thirties",
        "athletic man in his forties", "athletic man in his early fifties",
    ],
    "Beide": [
        "athletic woman in her late twenties", "athletic man in his early thirties",
        "athletic woman in her forties", "athletic man in his fifties",
    ],
    "Non-binair en trans": [
        "athletic non-binary adult", "athletic transgender woman",
        "athletic transgender man", "athletic gender-diverse adult",
    ],
}


def default_scenes(cast: str = "Beide") -> list[Scene]:
    people = CASTS.get(cast, CASTS["Beide"])
    outfits = [
        "electric-blue performance outfit", "black and orange technical sportswear",
        "silver futuristic training set", "deep-green premium activewear",
        "purple and gold dance-fitness outfit", "red high-fashion sportswear",
        "white championship outfit",
    ]
    return [
        Scene(people[i % len(people)], outfits[i], LANDMARKS[i])
        for i in range(7)
    ]


def countdown_value(t: float) -> str:
    if t < 1:
        return "READY"
    return str(max(0, COUNT_FROM - int(t - 1)))


def _vertical(clip, size: tuple[int, int]):
    from moviepy.video.fx import Crop, Resize
    width, height = size
    target_ratio = width / height
    ratio = clip.w / clip.h
    if ratio > target_ratio:
        clip = clip.with_effects([Crop(x_center=clip.w / 2, width=int(clip.h * target_ratio), height=clip.h)])
    else:
        clip = clip.with_effects([Crop(y_center=clip.h / 2, width=clip.w, height=int(clip.w / target_ratio))])
    return clip.with_effects([Resize(size)])


def render_countdown(
    clip_paths: Iterable[Path],
    output_path: Path,
    music_path: Path | None = None,
    size: tuple[int, int] = (1080, 1920),
    progress: Callable[[str], None] | None = None,
) -> Path:
    from moviepy import (
        AudioFileClip,
        CompositeAudioClip,
        CompositeVideoClip,
        VideoFileClip,
        concatenate_videoclips,
    )
    from moviepy.video.VideoClip import TextClip
    paths = [Path(p) for p in clip_paths]
    if not paths:
        raise ValueError("Voeg minimaal één video toe.")
    opened: list[VideoFileClip] = []
    pieces = []
    try:
        remaining = TOTAL_SECONDS
        index = 0
        while remaining > 0:
            source = VideoFileClip(str(paths[index % len(paths)]), audio=False)
            opened.append(source)
            duration = min(SEGMENT_SECONDS, remaining)
            if source.duration < duration:
                loops = int(duration / source.duration) + 1
                source = concatenate_videoclips([source] * loops).subclipped(0, duration)
            else:
                source = source.subclipped(0, duration)
            pieces.append(_vertical(source, size))
            remaining -= duration
            index += 1

        timeline = concatenate_videoclips(pieces, method="compose").with_duration(TOTAL_SECONDS)
        timer = TextClip(
            text=countdown_value, font_size=260, color="white", stroke_color="black",
            stroke_width=8, method="label", duration=TOTAL_SECONDS,
        ).with_position(("center", 0.72), relative=True)
        final = CompositeVideoClip([timeline, timer], size=size).with_duration(TOTAL_SECONDS)

        if music_path:
            music = AudioFileClip(str(music_path))
            loops = int(TOTAL_SECONDS / music.duration) + 1
            audio = CompositeAudioClip([music.with_start(i * music.duration) for i in range(loops)])
            final = final.with_audio(audio.with_duration(TOTAL_SECONDS))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if progress:
            progress("62 seconden monteren en countdown toevoegen...")
        final.write_videofile(
            str(output_path), fps=30, codec="libx264", audio_codec="aac",
            preset="medium", threads=4, logger=None,
        )
        return output_path
    finally:
        for clip in opened:
            clip.close()
