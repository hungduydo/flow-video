"""
Central registry of all pipeline steps.

Each StepInfo declares:
  id           — unique identifier used by check_prerequisites()
  name         — human-readable name shown in logs and error messages
  description  — one-line description of what the step does
  sentinel     — filename this step writes on success (e.g. ".step2.done")
  dependencies — tuple of step IDs that ALL must be done before this step runs
  dep_any      — tuple of step IDs where AT LEAST ONE must be done

Usage:
    from pipeline.registry import REGISTRY, StepInfo

    info = REGISTRY["step4_translate"]
    print(info.name)         # → "Translate"
    print(info.sentinel)     # → ".step4.done"
    print(info.dependencies) # → ("step3_transcribe",)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepInfo:
    id: str
    name: str
    description: str
    sentinel: str
    dependencies: tuple[str, ...] = ()
    dep_any: tuple[str, ...] = ()


REGISTRY: dict[str, StepInfo] = {s.id: s for s in [
    StepInfo(
        id="step1_download",
        name="Download",
        description="Download Bilibili video via yt-dlp",
        sentinel=".step1.done",
    ),
    StepInfo(
        id="step1b_scenes",
        name="Scene Detection",
        description="Detect visual scene cuts → scenes.json",
        sentinel=".step1b.done",
        dependencies=("step1_download",),
    ),
    StepInfo(
        id="step1c_remove_logo",
        name="Remove Logo",
        description="Remove watermarks/logos via LLM + ffmpeg delogo",
        sentinel=".step1c.done",
        dependencies=("step1_download",),
    ),
    StepInfo(
        id="step2_extract_audio",
        name="Extract Audio",
        description="Extract audio.wav (16 kHz mono PCM) from original.mp4",
        sentinel=".step2.done",
        dependencies=("step1_download",),
    ),
    StepInfo(
        id="step2b_separate_audio",
        name="Separate Audio",
        description="Separate vocals/accompaniment via Demucs",
        sentinel=".step2b.done",
        dependencies=("step2_extract_audio",),
    ),
    StepInfo(
        id="step2c_classify",
        name="Classify",
        description="Classify video type by audio analysis",
        sentinel=".step2c.done",
        dependencies=("step2_extract_audio",),
    ),
    StepInfo(
        id="step3_transcribe",
        name="Transcribe",
        description="Speech-to-text (Whisper/Deepgram) → captions_cn.srt",
        sentinel=".step3.done",
        dependencies=("step2_extract_audio",),
    ),
    StepInfo(
        id="step4_translate",
        name="Translate",
        description="Translate captions CN → VN (Gemini/Claude)",
        sentinel=".step4.done",
        dependencies=("step3_transcribe",),
    ),
    StepInfo(
        id="step5_tts",
        name="TTS",
        description="Generate Vietnamese TTS audio → audio_vn_full.mp3",
        sentinel=".step5.done",
        dependencies=("step4_translate",),
    ),
    StepInfo(
        id="step6_compose",
        name="Compose",
        description="Compose final video with burned-in captions",
        sentinel=".step6.done",
        dependencies=("step4_translate", "step5_tts"),
    ),
    # Virtual entries for per-platform step6 sentinels — used by step7's dep_any
    StepInfo(
        id="step6_compose_youtube",
        name="Compose (YouTube)",
        description="Compose YouTube 16:9 final video",
        sentinel=".step6.youtube.done",
    ),
    StepInfo(
        id="step6_compose_tiktok",
        name="Compose (TikTok)",
        description="Compose TikTok 9:16 final video",
        sentinel=".step6.tiktok.done",
    ),
    StepInfo(
        id="step7_banner",
        name="Banner",
        description="Generate YouTube/TikTok banner thumbnails via LLM",
        sentinel=".step7.done",
        dep_any=("step6_compose_youtube", "step6_compose_tiktok"),
    ),
]}
