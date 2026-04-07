"""
Step 5: Vietnamese captions_vn.srt → per-segment TTS audio → audio_vn_full.mp3

Uses edge-tts (Microsoft Edge TTS, free, no API key) with vi-VN-HoaiMyNeural.
All segments are generated at natural speed, then a single global speed adjustment
(atempo, clamped 0.9–1.2x) is applied to the merged audio to match the original
audio duration. This avoids per-segment mechanical stretching.

Flow:
  1. Generate each TTS segment at natural speed
  2. Concatenate all segments + silence gaps → audio_vn_speech.mp3
  3. Compare duration of audio_vn_speech.mp3 vs original audio.wav
  4. Apply one atempo pass (0.9–1.2x) to match durations
  5. Mix with accompaniment if available

Output:
  output/{video_id}/audio_vn/seg_NNN.mp3   (natural-speed TTS per segment)
  output/{video_id}/audio_vn_speech.mp3    (concatenated, before speed adjust)
  output/{video_id}/audio_vn_full.mp3      (final, speed-adjusted + mixed)
  output/{video_id}/.step5.done            (sentinel)
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
import srt
from tqdm import tqdm

VOICE = "vi-VN-HoaiMyNeural"
MIN_DURATION = 0.3   # seconds — skip TTS for extremely short segments
SPEED_MIN = 0.9      # atempo lower bound
SPEED_MAX = 1.2      # atempo upper bound


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_audio_duration(path: Path) -> float:
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


async def _tts_segment(text: str, output_path: Path) -> None:
    """Generate TTS audio for a single text segment at natural speed."""
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(output_path))


_AUDIO_FILTER = (
    "highpass=f=80,"
    "lowpass=f=12000,"
    "equalizer=f=100:width_type=o:width=2:g=3,"
    "equalizer=f=3000:width_type=o:width=2:g=2,"
    "acompressor=threshold=-18dB:ratio=4:attack=5:release=50,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


def _enhance_audio(input_path: Path, output_path: Path) -> None:
    """Apply EQ, compression, echo, and loudness normalization to a TTS segment."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", _AUDIO_FILTER,
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"audio enhance failed for {input_path}:\n{result.stderr}")


def _generate_silence(output: Path, duration: float) -> None:
    """Generate a silent MP3 of the given duration."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"silence generation failed:\n{result.stderr}")


def _concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate segments into one MP3 using ffmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in segment_paths:
            safe = str(p.resolve()).replace("'", "'\\''")
            f.write(f"file '{safe}'\n")
        concat_list = Path(f.name)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr}")


def _apply_global_speed(input_path: Path, output_path: Path, vn_duration: float, original_duration: float) -> None:
    """Apply a single atempo pass (clamped 0.9–1.2x) so vn audio matches original duration."""
    ratio = vn_duration / original_duration
    ratio = max(SPEED_MIN, min(SPEED_MAX, ratio))
    print(f"[step5] Speed adjust: {vn_duration:.1f}s → {original_duration:.1f}s  atempo={ratio:.4f}")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", f"atempo={ratio:.4f}",
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"atempo failed:\n{result.stderr}")


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
        raise RuntimeError(f"audio mix failed:\n{result.stderr}")


# ── Main ─────────────────────────────────────────────────────────────────────

def generate_tts(output_dir: Path) -> Path:
    sentinel = output_dir / ".step5.done"
    if sentinel.exists():
        print("[step5] Skip — audio_vn_full.mp3 already generated")
        return output_dir / "audio_vn_full.mp3"

    vn_srt_path = output_dir / "captions_vn.srt"
    if not vn_srt_path.exists():
        raise FileNotFoundError(f"captions_vn.srt not found in {output_dir}")

    audio_vn_dir = output_dir / "audio_vn"
    audio_vn_dir.mkdir(exist_ok=True)

    subtitles = list(srt.parse(vn_srt_path.read_text(encoding="utf-8")))
    print(f"[step5] Generating TTS for {len(subtitles)} segments (voice: {VOICE}) …")

    all_paths: list[Path] = []
    prev_end = 0.0

    for i, sub in enumerate(tqdm(subtitles, desc="[step5] TTS", unit="seg")):
        sub_start = sub.start.total_seconds()
        sub_end = sub.end.total_seconds()
        idx = f"{sub.index:04d}"

        # Insert silence for any gap before this segment
        gap = sub_start - prev_end
        if gap > 0.05:
            gap_path = audio_vn_dir / f"gap_{i:04d}.mp3"
            _generate_silence(gap_path, gap)
            all_paths.append(gap_path)

        original_duration = (sub.end - sub.start).total_seconds()
        text = sub.content.strip()

        if not text or original_duration < MIN_DURATION:
            sil_path = audio_vn_dir / f"seg_{idx}_sil.mp3"
            _generate_silence(sil_path, max(original_duration, 0.1))
            all_paths.append(sil_path)
            prev_end = sub_end
            continue

        seg_path = audio_vn_dir / f"seg_{idx}.mp3"
        asyncio.run(_tts_segment(text, seg_path))
        all_paths.append(seg_path)
        prev_end = sub_end

    # Concatenate all segments + gaps into one file
    speech_path = output_dir / "audio_vn_speech.mp3"
    print("[step5] Concatenating segments …")
    _concat_segments(all_paths, speech_path)

    # Compare with original audio and apply a single global speed adjustment
    original_audio = output_dir / "audio.wav"
    vn_duration = _get_audio_duration(speech_path)
    original_duration = _get_audio_duration(original_audio) if original_audio.exists() else 0.0

    speed_adjusted_path = output_dir / "audio_vn_speech_adjusted.mp3"
    if original_duration > 0 and vn_duration > 0:
        _apply_global_speed(speech_path, speed_adjusted_path, vn_duration, original_duration)
    else:
        print("[step5] WARNING: could not determine original duration, skipping speed adjust")
        speech_path.rename(speed_adjusted_path)

    # Apply EQ, compression, echo, and loudness normalization to the merged audio
    enhanced_path = output_dir / "audio_vn_speech_enhanced.mp3"
    print("[step5] Enhancing audio …")
    _enhance_audio(speed_adjusted_path, enhanced_path)

    # Mix with accompaniment (background music) if available
    full_audio_path = output_dir / "audio_vn_full.mp3"
    accompaniment_path = output_dir / "accompaniment.mp3"
    if accompaniment_path.exists():
        print("[step5] Mixing speech with accompaniment …")
        _mix_with_accompaniment(enhanced_path, accompaniment_path, full_audio_path)
    else:
        enhanced_path.rename(full_audio_path)

    sentinel.touch()
    print(f"[step5] Done — {full_audio_path}")
    return full_audio_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step5_tts <output_dir>")
        sys.exit(1)
    generate_tts(Path(sys.argv[1]))
