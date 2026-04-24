"""Orchestrator for intro segment generation."""

import logging
from pathlib import Path

from .generate_text import generate_intro
from .render_overlay import render_overlay
from .synthesis import synthesize_intro
from .compose_video import create_intro_video

logger = logging.getLogger(__name__)


def _parse_captions(captions_srt_path: Path) -> str:
    """Extract text from SRT file."""
    if not captions_srt_path.exists():
        return ""

    lines = []
    with open(captions_srt_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip timestamps and sequence numbers
            if line and not line.isdigit() and "-->" not in line:
                lines.append(line)

    return " ".join(lines[:10])  # First 10 caption lines


def intro(
    output_dir: Path,
    bg_image_path: Path,
    title: str,
    captions_srt_path: Path,
    video_path: Path = None,
    duration: float = 5.0,
    provider: str = "edge_tts",
    llm_provider: str = "claude",
) -> Path:
    """
    Generate intro segment video.

    Args:
        output_dir: Output directory
        bg_image_path: Path to background image
        title: Video title
        captions_srt_path: Path to captions SRT file
        video_path: Path to original_clean.mp4 (default: output_dir/original_clean.mp4)
        duration: Intro duration in seconds (default 5.0)
        provider: TTS provider ("edge_tts" or "elevenlabs")
        llm_provider: LLM provider ("claude" or "gemini")

    Returns:
        Path to intro_video.mp4
    """
    output_dir = Path(output_dir)
    bg_image_path = Path(bg_image_path)
    captions_srt_path = Path(captions_srt_path)

    # Determine video path
    if video_path is None:
        video_path = output_dir / "original_clean.mp4"
    else:
        video_path = Path(video_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not bg_image_path.exists():
        raise FileNotFoundError(f"Background image not found: {bg_image_path}")

    # Output paths
    intro_text_path = output_dir / "intro_text.txt"
    intro_audio_path = output_dir / "intro_audio_vn.mp3"
    overlay_path = output_dir / "overlay.png"
    intro_video_path = output_dir / "intro_video.mp4"
    sentinel = output_dir / ".step_intro.done"

    # Check sentinel
    if sentinel.exists():
        logger.info(f"Intro already generated, skipping (remove {sentinel} to regenerate)")
        return intro_video_path

    # Step 1: Generate intro text
    logger.info("Step 1: Generating intro text...")
    captions_sample = _parse_captions(captions_srt_path)
    intro_text = generate_intro(title, captions_sample, llm_provider=llm_provider)

    # Save intro text
    intro_text_path.write_text(intro_text, encoding="utf-8")
    logger.info(f"Intro text saved: {intro_text_path}")

    # Step 2: Generate TTS audio
    logger.info("Step 2: Generating TTS audio...")
    intro_audio_path, audio_duration = synthesize_intro(
        intro_text,
        intro_audio_path,
        provider=provider,
    )
    logger.info(f"Audio duration: {audio_duration:.2f}s")

    # Adjust duration to match audio
    # Use max of 5s and audio duration
    final_duration = max(duration, audio_duration + 0.5)

    # Step 3: Render overlay
    logger.info("Step 3: Rendering overlay...")
    render_overlay(
        bg_image_path,
        intro_text,
        overlay_path,
    )

    # Step 4: Compose video
    logger.info("Step 4: Composing video...")
    create_intro_video(
        video_path,
        overlay_path,
        intro_audio_path,
        intro_video_path,
        duration=final_duration,
    )

    # Write sentinel
    sentinel.write_text("done\n")

    logger.info(f"✓ Intro generation complete: {intro_video_path}")
    return intro_video_path
