"""
Step 2: Extract audio from original.mp4 → audio.wav (16 kHz mono, PCM).

16 kHz mono is the format faster-whisper expects for best accuracy.

Output:
  output/{video_id}/audio.wav
  output/{video_id}/.step2.done  (sentinel)
"""

import subprocess
import sys
from pathlib import Path

from pipeline.prereqs import check_prerequisites


def extract_audio(output_dir: Path) -> Path:
    sentinel = output_dir / ".step2.done"
    if sentinel.exists():
        print("[step2] Skip — audio.wav already extracted")
        return output_dir / "audio.wav"

    check_prerequisites("step2_extract_audio", output_dir)

    video_path = output_dir / "original.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"original.mp4 not found in {output_dir}")

    wav_path = output_dir / "audio.wav"
    print("[step2] Extracting audio …")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ar", "16000",   # 16 kHz sample rate
        "-ac", "1",        # mono
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr}")

    sentinel.touch()
    print(f"[step2] Done — {wav_path}")
    return wav_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step2_extract_audio <output_dir>")
        sys.exit(1)
    extract_audio(Path(sys.argv[1]))
