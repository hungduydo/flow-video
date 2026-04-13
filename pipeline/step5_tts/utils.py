"""Shared audio utilities for step 5 (TTS synthesis and assembly)."""

import subprocess
from pathlib import Path


def get_audio_duration(path: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 0.0
    return float(result.stdout.strip())


def generate_silence(output: Path, duration: float, sample_rate: int = 24000, channels: str = "mono") -> None:
    """Generate a silent MP3 of the given duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl={channels}",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"silence generation failed:\n{result.stderr}")
