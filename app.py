from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
REPO = HERE
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env")

from countdown_core import Scene, default_scenes, render_countdown

try:
    from kling_client import FitnessKlingClient
except ImportError:
    FitnessKlingClient = None

st.set_page_config(page_title="AI Countdown Studio", page_icon="⏱️", layout="wide")
st.title("⏱️ AI Countdown Studio")
st.caption("Maak een verticale 62-secondenvideo: 1 seconde READY + exact 60 naar 0.")

if "run_id" not in st.session_state:
    st.session_state.run_id = uuid.uuid4().hex[:8]
project_dir = REPO / "projects" / f"countdown_{st.session_state.run_id}"
for folder in ("uploads", "clips", "output"):
    (project_dir / folder).mkdir(parents=True, exist_ok=True)

with st.sidebar:
    st.header("Productie")
    kling_key = st.text_input("Kling API key", value=os.getenv("KLING_API_KEY", ""), type="password")
    quality = st.selectbox("Kling kwaliteit", ["Standard", "Professional"])
    st.metric("Totale lengte", "62 sec")
    st.caption("Formaat: 9:16 · 1080x1920 · 30 fps")
    st.warning("Gebruik alleen muziek waarvoor je publicatie- en monetisatierechten hebt.")

tab_plan, tab_generate, tab_finish = st.tabs(
    ["1. Personen & scènes", "2. AI-clips", "3. Countdown & muziek"]
)

scenes: list[Scene] = []
with tab_plan:
    cast_choice = st.radio(
        "Wie telt af?",
        [
            "Dezelfde vrouw", "Dezelfde man",
            "Wisselende vrouwen", "Wisselende mannen",
            "Beide", "Non-binair en trans",
        ],
        horizontal=True,
        help="De gekozen groep wordt verdeeld over alle zeven wereldscènes.",
    )
    st.subheader("Zeven wisselmomenten")
    st.write("Pas per scène persoon, kleding en omgeving aan. De blik-in-camera-instructie wordt automatisch toegevoegd.")
    for i, preset in enumerate(default_scenes(cast_choice)):
        with st.expander(f"Scène {i + 1} · vanaf ongeveer {i * 10} sec", expanded=i < 2):
            c1, c2, c3 = st.columns(3)
            person = c1.text_input("AI-persoon", preset.person, key=f"person_{i}")
            clothing = c2.text_input("Kleding", preset.clothing, key=f"clothing_{i}")
            environment = c3.text_input("Omgeving", preset.environment, key=f"env_{i}")
            scene = Scene(person, clothing, environment)
            scenes.append(scene)
            st.code(scene.prompt(), language=None)

with tab_generate:
    st.subheader("Maak of upload de scèneclips")
    st.info(
        "Beste resultaat: gebruik per scène een AI-character-afbeelding en één rustige motion-reference "
        "waarin iemand recht in de camera kijkt. Kling zet de beweging over op de AI-persoon."
    )
    same_person = cast_choice in ("Dezelfde vrouw", "Dezelfde man")
    shared_image = None
    if same_person:
        st.success(
            "Identiteitsmodus actief: upload hieronder één AI-personage. "
            "Dezelfde referentie wordt bij alle zeven wereldscènes gebruikt."
        )
        shared_image = st.file_uploader(
            "Gedeelde AI-characterafbeelding",
            ["png", "jpg", "jpeg", "webp"],
            key="shared_identity_image",
        )
    for i, scene in enumerate(scenes):
        st.markdown(f"#### Scène {i + 1}")
        c1, c2, c3 = st.columns(3)
        image = shared_image if same_person else c1.file_uploader(
            "AI-personage", ["png", "jpg", "jpeg", "webp"], key=f"image_{i}"
        )
        if same_person:
            c1.caption("Gedeelde identiteit")
        motion = c2.file_uploader("Blik/mond-motion", ["mp4", "mov", "m4v"], key=f"motion_{i}")
        ready = c3.file_uploader("Of kant-en-klare AI-clip", ["mp4", "mov", "m4v"], key=f"ready_{i}")
        clip_path = project_dir / "clips" / f"scene_{i + 1:02d}.mp4"
        if ready:
            clip_path.write_bytes(ready.getbuffer())
        if clip_path.exists():
            st.video(str(clip_path))
        if st.button(f"Genereer scène {i + 1} met Kling", key=f"generate_{i}"):
            if not kling_key:
                st.error("Vul eerst de Kling API key in.")
            elif FitnessKlingClient is None:
                st.error("Kling-module kon niet worden geladen.")
            elif not image or not motion:
                st.error("Upload voor deze scène een AI-personage en motion-reference.")
            else:
                image_path = project_dir / "uploads" / (
                    "shared_character.png" if same_person else f"scene_{i + 1:02d}_character.png"
                )
                motion_path = project_dir / "uploads" / f"scene_{i + 1:02d}_motion.mp4"
                image_path.write_bytes(image.getbuffer())
                motion_path.write_bytes(motion.getbuffer())
                try:
                    with st.status("Kling genereert de scène...", expanded=True) as status:
                        client = FitnessKlingClient(kling_key)
                        client.generate_motion_control(
                            character_image=image_path,
                            reference_video=motion_path,
                            output_path=clip_path,
                            prompt=scene.prompt(),
                            mode="pro" if quality == "Professional" else "std",
                            character_orientation="image",
                            progress=lambda message: st.write(message),
                        )
                        status.update(label="Scène klaar", state="complete")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Kling-generatie mislukt: {exc}")

with tab_finish:
    st.subheader("Exacte countdown en soundtrack")
    st.write("De cijfers worden lokaal over de video gezet. Daardoor klopt iedere seconde exact.")
    discovered = sorted((project_dir / "clips").glob("scene_*.mp4"))
    st.write(f"Beschikbare scènes: **{len(discovered)}**")
    music = st.file_uploader(
        "Upload rechtenvrije of gelicentieerde housemuziek",
        ["mp3", "wav", "m4a", "aac"],
        help="Energieke festival/deep-house met een duidelijke build-up werkt goed.",
    )
    if st.button("🎬 MAAK COUNTDOWNVIDEO", type="primary", use_container_width=True):
        if not discovered:
            st.error("Genereer of upload eerst minimaal één scèneclip.")
            st.stop()
        music_path = None
        if music:
            music_path = project_dir / "uploads" / f"soundtrack{Path(music.name).suffix.lower()}"
            music_path.write_bytes(music.getbuffer())
        output = project_dir / "output" / "ai_countdown_62s.mp4"
        status = st.empty()
        try:
            render_countdown(discovered, output, music_path, progress=status.info)
            status.success("Klaar: 62 seconden, READY + 60 naar 0.")
            st.video(str(output))
            st.download_button(
                "⬇️ Download MP4", output.read_bytes(), "ai_countdown_62s.mp4",
                "video/mp4", use_container_width=True,
            )
        except Exception as exc:
            status.error(f"Montage mislukt: {exc}")

st.caption(
    "AI Countdown Studio · label AI-personen waar het platform dat vereist · "
    "gebruik geen echte persoon zonder toestemming."
)
