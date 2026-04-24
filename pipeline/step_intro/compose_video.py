"""Create intro video by compositing video clip + overlay image + audio."""

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Get video width and height using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        width, height = map(int, result.stdout.strip().split("x"))
        return width, height
    except Exception as e:
        logger.error(f"Failed to get video dimensions: {e}")
        return 1920, 1080  # Fallback


def create_intro_video(
    video_path: Path,
    overlay_path: Path,
    audio_path: Path,
    output_path: Path,
    duration: float = 5.0,
) -> Path:
    """
    Create intro video by compositing video clip + overlay + audio.

    Args:
        video_path: Path to original_clean.mp4
        overlay_path: Path to overlay.png
        audio_path: Path to intro_audio_vn.mp3
        output_path: Path to save intro_video.mp4
        duration: Video clip duration in seconds (default 5.0)

    Returns:
        Path to intro_video.mp4
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get video dimensions
    width, height = _get_video_dimensions(video_path)
    overlay_y = (height * 2) // 3  # Bottom 1/3

    logger.info(f"Video dimensions: {width}×{height}, overlay at y={overlay_y}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Step 1: Crop video to first N seconds (fast, no re-encoding)
        cropped_video = tmpdir / "intro_cropped.mp4"
        _crop_video(video_path, cropped_video, duration)

        # Step 2: Composite video + overlay + audio
        _composite_video(
            cropped_video,
            overlay_path,
            audio_path,
            output_path,
            overlay_y=overlay_y,
            duration=duration,
        )

    logger.info(f"Intro video saved: {output_path}")
    return output_path


def _crop_video(input_path: Path, output_path: Path, duration: float) -> None:
    """Crop video to first N seconds (fast, using -c copy)."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-t",
        str(duration),
        "-c",
        "copy",
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Video cropped: {output_path} ({duration}s)")
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg crop failed: {e.stderr.decode()}")
        raise


def _composite_video(
    video_path: Path,
    overlay_path: Path,
    audio_path: Path,
    output_path: Path,
    overlay_y: int,
    duration: float,
) -> None:
    """Composite video + overlay + audio using ffmpeg."""
    # Filter: overlay PNG at specified Y position
    filter_complex = (
        f"[0:v][1:v]overlay=0:{overlay_y}:enable='between(t,0,{duration})'[v]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(overlay_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]:v",  # Use composite video
        "-map",
        "2:a",  # Use audio from 3rd input
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-t",
        str(duration),
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info(f"Video composition complete: {output_path}")
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg composition failed: {e.stderr.decode()}")
        raise
