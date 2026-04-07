"""
Step 2b: Separate vocals and accompaniment using Demucs.

Splits audio.wav into two stems:
  vocals.wav         — speech only (resampled to 16 kHz mono for transcription)
  accompaniment.wav  — background music (original quality, for final mix)

Uses the htdemucs model (Meta, 2-stem mode: vocals + no_vocals).

Output:
  output/{video_id}/vocals.wav
  output/{video_id}/accompaniment.wav
  output/{video_id}/.step2b.done  (sentinel)
"""

import shutil
import subprocess
import sys
from pathlib import Path


def separate_audio(output_dir: Path) -> tuple[Path, Path]:
    sentinel = output_dir / ".step2b.done"
    vocals_path = output_dir / "vocals.wav"
    accompaniment_path = output_dir / "accompaniment.mp3"

    if sentinel.exists():
        print("[step2b] Skip — vocals.wav / accompaniment.wav already exist")
        return vocals_path, accompaniment_path

    wav_path = output_dir / "audio.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"audio.wav not found in {output_dir}")

    demucs_out = output_dir / "demucs_tmp"
    demucs_out.mkdir(exist_ok=True)

    print("[step2b] Separating vocals and accompaniment (Demucs htdemucs 2-stem) …")
    print("        (first run downloads ~80 MB model — be patient)")
    cmd = [
        "python", "-m", "demucs",
        "-n", "htdemucs",
        "--two-stems", "vocals",
        "--mp3",
        "--mp3-bitrate", "320",
        "--out", str(demucs_out),
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"demucs failed:\n{result.stderr}")

    # Demucs writes to: demucs_tmp/htdemucs/<stem_name>/vocals.mp3 + no_vocals.mp3
    stem_dir = demucs_out / "htdemucs" / wav_path.stem
    raw_vocals = stem_dir / "vocals.mp3"
    raw_no_vocals = stem_dir / "no_vocals.mp3"

    if not raw_vocals.exists() or not raw_no_vocals.exists():
        raise FileNotFoundError(f"Demucs output not found in {stem_dir}")

    # Resample vocals to 16 kHz mono (faster-whisper expects this format)
    print("[step2b] Resampling vocals to 16 kHz mono …")
    resample_cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_vocals),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(vocals_path),
    ]
    result = subprocess.run(resample_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"vocals resample failed:\n{result.stderr}")

    # Keep accompaniment at original quality for the final audio mix
    shutil.copy2(raw_no_vocals, accompaniment_path)

    shutil.rmtree(demucs_out, ignore_errors=True)

    sentinel.touch()
    print(f"[step2b] Done — {vocals_path.name}, {accompaniment_path.name}")
    return vocals_path, accompaniment_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step2b_separate_audio <output_dir>")
        sys.exit(1)
    separate_audio(Path(sys.argv[1]))
