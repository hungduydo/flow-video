"""
Step 5b: Assemble per-segment TTS audio into the final audio_vn_full.mp3.

Each segment is placed at its EXACT SRT start time using ffmpeg adelay+amix.
If a segment's TTS runs longer than its slot, it blends (not trimmed) with the
next segment's audio. No global speed adjustment is needed because timing comes
directly from the SRT timestamps.

Output:
  output/{video_id}/audio_vn_speech.mp3   (all segments at exact SRT positions)
  output/{video_id}/audio_vn_full.mp3     (mixed with accompaniment if present)
  output/{video_id}/.step5b.done          (sentinel)
"""

import shutil
import subprocess
import sys
from pathlib import Path

import srt

from .utils import get_audio_duration, generate_silence


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_speech_timeline(
    subtitles: list,
    audio_vn_dir: Path,
    output_path: Path,
    original_duration: float,
) -> bool:
    """Place each TTS segment at its exact SRT start time using adelay+amix.

    Segments that overflow their slot blend with adjacent audio rather than
    being trimmed. Total output is capped to original_duration if provided.

    Returns True on success, False if no segments were found.
    """
    items: list[tuple[Path, int]] = []
    for sub in subtitles:
        seg_path = audio_vn_dir / f"seg_{sub.index:04d}.mp3"
        if seg_path.exists():
            delay_ms = int(sub.start.total_seconds() * 1000)
            items.append((seg_path, delay_ms))

    if not items:
        return False

    print(f"[step5b] Placing {len(items)} segments on timeline …")

    cmd = ["ffmpeg", "-y"]
    for seg_path, _ in items:
        cmd += ["-i", str(seg_path)]

    filter_parts = [
        f"[{i}:a]atempo=1.1,adelay={delay_ms}|{delay_ms}[a{i}]"
        for i, (_, delay_ms) in enumerate(items)
    ]
    mix_inputs = "".join(f"[a{i}]" for i in range(len(items)))
    filter_complex = (
        ";".join(filter_parts)
        + f";{mix_inputs}amix=inputs={len(items)}:duration=longest:normalize=0[out]"
    )

    cmd += ["-filter_complex", filter_complex, "-map", "[out]"]
    if original_duration > 0:
        cmd += ["-t", str(original_duration)]
    cmd += ["-c:a", "libmp3lame", "-q:a", "4", str(output_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Timeline build failed:\n{result.stderr[-3000:]}")
    return True


def _mix_with_accompaniment(speech_path: Path, accompaniment_path: Path, output_path: Path) -> None:
    """Mix speech audio with background accompaniment track."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(speech_path),
        "-i", str(accompaniment_path),
        "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio mix failed:\n{result.stderr}")


# ── Main ─────────────────────────────────────────────────────────────────────

def assemble_audio(output_dir: Path) -> Path:
    """Assemble per-segment TTS files into audio_vn_full.mp3.

    Reads captions_vn.srt to determine exact start times, then places each
    audio_vn/seg_NNNN.mp3 at its corresponding SRT timestamp using adelay+amix.

    Args:
        output_dir: pipeline output directory (must contain audio_vn/ from step 5a)

    Returns:
        Path to audio_vn_full.mp3
    """
    output_dir = Path(output_dir).resolve()
    sentinel = output_dir / ".step5b.done"
    if sentinel.exists():
        print("[step5b] Skip — audio already assembled")
        return output_dir / "audio_vn_full.mp3"

    vn_srt_path = output_dir / "captions_vn.srt"
    if not vn_srt_path.exists():
        raise FileNotFoundError(f"captions_vn.srt not found in {output_dir}")

    audio_vn_dir = output_dir / "audio_vn"
    if not audio_vn_dir.exists():
        raise FileNotFoundError("audio_vn/ not found — run step 5a first")

    subtitles = list(srt.parse(vn_srt_path.read_text(encoding="utf-8")))
    print(f"[step5b] Assembling {len(subtitles)} segments …")

    # Original audio duration — used to cap timeline output
    original_audio = output_dir / "audio.wav"
    original_duration = get_audio_duration(original_audio) if original_audio.exists() else 0.0

    full_audio_path = output_dir / "audio_vn_full.mp3"
    accompaniment_path = output_dir / "accompaniment.mp3"

    speech_path = output_dir / "audio_vn_speech.mp3"
    built = _build_speech_timeline(subtitles, audio_vn_dir, speech_path, original_duration)

    if not built:
        # Music-only video — fall back to original/accompaniment audio
        print("[step5b] No segments found — using original audio")
        if accompaniment_path.exists():
            shutil.copy2(accompaniment_path, full_audio_path)
        elif original_audio.exists():
            cmd = [
                "ffmpeg", "-y", "-i", str(original_audio),
                "-c:a", "libmp3lame", "-q:a", "4", str(full_audio_path),
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        sentinel.touch()
        print(f"[step5b] Done — {full_audio_path}")
        return full_audio_path

    # Mix with accompaniment (background music) if available
    if accompaniment_path.exists():
        print("[step5b] Mixing speech with accompaniment …")
        _mix_with_accompaniment(speech_path, accompaniment_path, full_audio_path)
    else:
        shutil.copy2(speech_path, full_audio_path)

    sentinel.touch()
    vn_dur = get_audio_duration(full_audio_path)
    print(f"[step5b] Done — {full_audio_path}  ({vn_dur:.1f}s)")
    return full_audio_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step5_tts.step5b_assemble <output_dir>")
        sys.exit(1)
    assemble_audio(Path(sys.argv[1]))
