"""
Step 5: Vietnamese captions_vn.srt → per-segment TTS audio → audio_vn_full.mp3

Uses a pluggable TTSProvider (edge_tts by default, or elevenlabs via --tts-provider).
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

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import srt
from tqdm import tqdm

from .tts_providers import TTSProvider, get_provider

MIN_DURATION = 0.3   # seconds — skip TTS for extremely short segments
SPEED_MIN = 0.9      # atempo lower bound (global safety pass)
SPEED_MAX = 1.2      # atempo upper bound (global safety pass)
_SLOT_TOLERANCE = 0.05   # seconds — ignore slot diff smaller than this
_SLOT_MAX_ATEMPO = 1.30  # per-segment: compress up to 1.30× before trimming


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


def _is_speakable(text: str) -> bool:
    """Return True if text contains at least one letter or digit.

    Punctuation-only strings (e.g. '...', '???', '!!!') cause edge-tts to
    return NoAudioReceived, so we skip them and insert silence instead.
    """
    return bool(re.search(r"[A-Za-z\d\u00C0-\u024F\u1E00-\u1EFF]", text))


def _generate_silence(output: Path, duration: float, sample_rate: int = 24000, channels: str = "mono") -> None:
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


def _has_cut_in_range(cuts: set[float], start: float, end: float) -> bool:
    """Return True if any cut falls within [start, end] (inclusive boundaries)."""
    return any(start <= c <= end for c in cuts)


def _earliest_cut_in_range(cuts: set[float], start: float, end: float) -> float | None:
    """Return the earliest cut strictly inside (start, end), or None."""
    in_range = [c for c in cuts if start < c < end]
    return min(in_range) if in_range else None


def _trim_audio(input_path: Path, output_path: Path, duration: float) -> None:
    """Trim audio to at most `duration` seconds using ffmpeg -t."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-t", str(duration),
        "-c:a", "libmp3lame", "-q:a", "4",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"audio trim failed:\n{result.stderr}")


def _fit_to_slot(
    seg_path: Path,
    slot_duration: float,
    audio_vn_dir: Path,
    idx: str,
    fmt: dict,
) -> list[Path]:
    """Return paths that together fill exactly slot_duration seconds.

    - Within 50 ms: [seg_path] unchanged
    - TTS shorter than slot: [seg_path, pad_silence]
    - TTS up to 1.30× longer: [atempo-compressed]
    - TTS > 1.30× longer: [trimmed to slot]
    """
    tts_dur = _get_audio_duration(seg_path)
    diff = tts_dur - slot_duration

    if abs(diff) <= _SLOT_TOLERANCE:
        return [seg_path]

    if diff < 0:
        pad_path = audio_vn_dir / f"seg_{idx}_pad.mp3"
        _generate_silence(pad_path, -diff, fmt["sample_rate"], fmt["channels"])
        return [seg_path, pad_path]

    ratio = tts_dur / slot_duration
    if ratio <= _SLOT_MAX_ATEMPO:
        fitted_path = audio_vn_dir / f"seg_{idx}_fitted.mp3"
        cmd = [
            "ffmpeg", "-y", "-i", str(seg_path),
            "-af", f"atempo={ratio:.4f}",
            "-c:a", "libmp3lame", "-q:a", "4",
            str(fitted_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"atempo failed:\n{result.stderr}")
        return [fitted_path]

    trimmed_path = audio_vn_dir / f"seg_{idx}_trim.mp3"
    _trim_audio(seg_path, trimmed_path, slot_duration)
    return [trimmed_path]


def _concat_segments(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate segments into one MP3 using ffmpeg concat demuxer."""
    if not segment_paths:
        raise RuntimeError("No segments to concatenate (all_paths is empty)")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for p in segment_paths:
            if not p.exists():
                raise RuntimeError(f"Segment file does not exist: {p}")
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

    # Show concat file content for debugging
    concat_content = concat_list.read_text() if concat_list.exists() else ""
    concat_list.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg concat failed (processed {len(segment_paths)} segments):\n"
            f"Concat file content:\n{concat_content}\n"
            f"Error:\n{result.stderr}"
        )


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

def generate_tts(output_dir: Path, provider: str = "edge_tts") -> Path:
    sentinel = output_dir / ".step5.done"
    if sentinel.exists():
        print("[step5] Skip — audio_vn_full.mp3 already generated")
        return output_dir / "audio_vn_full.mp3"

    vn_srt_path = output_dir / "captions_vn.srt"
    if not vn_srt_path.exists():
        raise FileNotFoundError(f"captions_vn.srt not found in {output_dir}")

    tts_provider: TTSProvider = get_provider(provider)
    fmt = tts_provider.audio_format

    audio_vn_dir = output_dir / "audio_vn"
    audio_vn_dir.mkdir(exist_ok=True)

    subtitles = list(srt.parse(vn_srt_path.read_text(encoding="utf-8")))
    print(f"[step5] Generating TTS for {len(subtitles)} segments (provider: {provider}) …")

    cuts: set[float] = set()
    scenes_path = output_dir / "scenes.json"
    if scenes_path.exists():
        data = json.loads(scenes_path.read_text(encoding="utf-8"))
        cuts = set(data.get("cuts", []))
        print(f"[step5] Loaded {len(cuts)} scene cut(s) from scenes.json")

    if provider == "elevenlabs":
        total_chars = sum(len(sub.content.strip()) for sub in subtitles)
        print(f"[step5] ElevenLabs: ~{total_chars:,} characters to synthesize")

    all_paths: list[Path] = []
    prev_end = 0.0

    for i, sub in enumerate(tqdm(subtitles, desc="[step5] TTS", unit="seg")):
        sub_start = sub.start.total_seconds()
        sub_end = sub.end.total_seconds()
        idx = f"{sub.index:04d}"

        # Insert silence for any gap before this segment.
        # Enforce MIN_DURATION gap at scene cut boundaries.
        gap = sub_start - prev_end
        if _has_cut_in_range(cuts, prev_end, sub_start):
            gap = max(gap, MIN_DURATION)
        if gap > 0.05:
            gap_path = audio_vn_dir / f"gap_{i:04d}.mp3"
            _generate_silence(gap_path, gap, fmt["sample_rate"], fmt["channels"])
            all_paths.append(gap_path)

        original_duration = (sub.end - sub.start).total_seconds()
        text = sub.content.strip()

        if not text or original_duration < MIN_DURATION or not _is_speakable(text):
            sil_path = audio_vn_dir / f"seg_{idx}_sil.mp3"
            _generate_silence(sil_path, max(original_duration, 0.1), fmt["sample_rate"], fmt["channels"])
            all_paths.append(sil_path)
            prev_end = sub_end
            continue

        seg_path = audio_vn_dir / f"seg_{idx}.mp3"
        try:
            tts_provider.synth(text, seg_path)
        except Exception as exc:
            tqdm.write(f"[step5] WARNING: TTS failed for seg {idx} ({text!r:.50}): {exc}; using silence")
            _generate_silence(seg_path, original_duration, fmt["sample_rate"], fmt["channels"])

        # Scene-cut trim: if a cut falls strictly inside this subtitle slot,
        # trim TTS to the cut and pad the remainder with silence so A/V sync holds.
        cut_inside = _earliest_cut_in_range(cuts, sub_start, sub_end)
        if cut_inside is not None:
            trim_duration = cut_inside - sub_start
            pad_duration = sub_end - cut_inside
            if trim_duration > MIN_DURATION:
                trimmed_path = audio_vn_dir / f"seg_{idx}_trim.mp3"
                _trim_audio(seg_path, trimmed_path, trim_duration)
                pad_path = audio_vn_dir / f"seg_{idx}_pad.mp3"
                _generate_silence(pad_path, pad_duration, fmt["sample_rate"], fmt["channels"])
                all_paths.append(trimmed_path)
                all_paths.append(pad_path)
            else:
                # Slot before the cut is too short — emit full silence for the slot
                sil_path = audio_vn_dir / f"seg_{idx}_cutsil.mp3"
                _generate_silence(sil_path, original_duration, fmt["sample_rate"], fmt["channels"])
                all_paths.append(sil_path)
        else:
            all_paths.extend(
                _fit_to_slot(seg_path, original_duration, audio_vn_dir, idx, fmt)
            )

        prev_end = sub_end

    # If no speakable segments (e.g. music-only video), skip TTS entirely
    if not all_paths:
        print("[step5] No speakable segments found — skipping TTS (music-only video)")
        full_audio_path = output_dir / "audio_vn_full.mp3"
        accompaniment_path = output_dir / "accompaniment.mp3"
        if accompaniment_path.exists():
            import shutil
            shutil.copy2(accompaniment_path, full_audio_path)
        elif (output_dir / "audio.wav").exists():
            cmd = [
                "ffmpeg", "-y", "-i", str(output_dir / "audio.wav"),
                "-c:a", "libmp3lame", "-q:a", "4", str(full_audio_path),
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        sentinel.touch()
        print(f"[step5] Done — {full_audio_path}")
        return full_audio_path

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
        ratio = vn_duration / original_duration
        if abs(ratio - 1.0) < 0.02:
            # Per-slot fitting already matched durations closely — skip global pass
            print(f"[step5] Duration drift {ratio:.4f} within 2% — no global speed adjust needed")
            import shutil as _shutil
            _shutil.copy2(speech_path, speed_adjusted_path)
        else:
            _apply_global_speed(speech_path, speed_adjusted_path, vn_duration, original_duration)
    else:
        print("[step5] WARNING: could not determine original duration, skipping speed adjust")
        speech_path.rename(speed_adjusted_path)

    # Mix with accompaniment (background music) if available
    full_audio_path = output_dir / "audio_vn_full.mp3"
    accompaniment_path = output_dir / "accompaniment.mp3"
    if accompaniment_path.exists():
        print("[step5] Mixing speech with accompaniment …")
        _mix_with_accompaniment(speed_adjusted_path, accompaniment_path, full_audio_path)
    else:
        speed_adjusted_path.rename(full_audio_path)

    sentinel.touch()
    print(f"[step5] Done — {full_audio_path}")
    return full_audio_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step5_tts <output_dir> [provider]")
        sys.exit(1)
    _provider = sys.argv[2] if len(sys.argv) > 2 else "edge_tts"
    generate_tts(Path(sys.argv[1]), provider=_provider)
