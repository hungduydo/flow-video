"""
Step 2c: Classify video type from audio.wav.

Analyzes audio features (silence ratio, voice energy, speech ratio, loudness)
to determine which processing workflow to use for subsequent steps.

Outputs:
  output/{video_id}/classification.json  — measured features + detected type
  output/{video_id}/.step2c.done         — sentinel to skip re-classification on resume

The detected video_type is also merged into metadata.json for easy access by
downstream steps without needing to read classification.json.

Usage:
  python -m pipeline.step2c_classify <output_dir> [model_size]
"""

import enum
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pipeline.prereqs import check_prerequisites


class VideoType(enum.Enum):
    MUSIC_VISUAL = "music"      # Group 1: Dance, DIY, Pets — keep original audio
    NARRATION    = "narration"  # Group 2: Story, Podcast, News — full voice replacement
    SILENT       = "silent"     # Group 3: ASMR, Cooking — keep ambient sounds
    REACTION     = "reaction"   # Group 4: Reaction/Commentary — PiP composition
    HYBRID       = "hybrid"     # Group 5: Vlog, Review — music + voice (narration pipeline)


def classify(output_dir: Path, model_size: str = "small") -> VideoType:
    """Analyze audio.wav and return the detected VideoType.

    Checks .step2c.done sentinel first; returns cached result if present.
    Also writes video_type into metadata.json for downstream steps.
    """
    sentinel = output_dir / ".step2c.done"
    result_path = output_dir / "classification.json"

    if sentinel.exists() and result_path.exists():
        saved = json.loads(result_path.read_text())
        vtype = VideoType(saved["video_type"])
        print(f"[step2c] Skip — cached result: {vtype.value}")
        return vtype

    check_prerequisites("step2c_classify", output_dir)

    wav_path = output_dir / "audio.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"audio.wav not found in {output_dir} — run step2 first")

    print("[step2c] Analyzing audio features …")

    duration           = _get_duration(wav_path)
    silence_ratio      = _measure_silence_ratio(wav_path, duration)
    voice_energy_ratio = _measure_voice_energy_ratio(wav_path)
    integrated_lufs, lra = _measure_ebur128(wav_path)

    # Music: moderately loud (not silence) AND stable dynamic range
    # Speech/narration has high LRA (> 12 LU); music has low LRA (< 12 LU)
    has_music = (integrated_lufs > -35.0) and (lra < 12.0)

    # speech_ratio: use existing SRT if transcription already ran (saves time)
    srt_path = output_dir / "captions_cn.srt"
    if srt_path.exists():
        speech_ratio = _speech_ratio_from_srt(srt_path, duration)
        print(f"[step2c] speech_ratio from SRT: {speech_ratio:.2f}")
    else:
        speech_ratio = _speech_ratio_from_whisper(wav_path, duration, model_size)
        print(f"[step2c] speech_ratio from Whisper ({model_size}): {speech_ratio:.2f}")

    video_type = _apply_rules(silence_ratio, voice_energy_ratio, speech_ratio, has_music)

    data = {
        "video_type":         video_type.value,
        "silence_ratio":      round(silence_ratio, 3),
        "voice_energy_ratio": round(voice_energy_ratio, 3),
        "speech_ratio":       round(speech_ratio, 3),
        "has_music":          has_music,
        "integrated_lufs":    round(integrated_lufs, 1),
        "lufs_lra":           round(lra, 1),
    }
    result_path.write_text(json.dumps(data, indent=2))

    _update_metadata(output_dir, video_type)

    sentinel.touch()

    print(
        f"[step2c] → {video_type.value}  "
        f"silence={silence_ratio:.2f}  voice_energy={voice_energy_ratio:.2f}  "
        f"speech={speech_ratio:.2f}  music={has_music}  "
        f"lufs={integrated_lufs:.1f}  lra={lra:.1f}"
    )
    return video_type


# ── Metadata ──────────────────────────────────────────────────────────────────

def _update_metadata(output_dir: Path, video_type: VideoType) -> None:
    """Merge video_type into metadata.json if it exists."""
    metadata_path = output_dir / "metadata.json"
    if not metadata_path.exists():
        return
    metadata = json.loads(metadata_path.read_text())
    metadata["video_type"] = video_type.value
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))


# ── Feature extraction ────────────────────────────────────────────────────────

def _get_duration(wav_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def _measure_silence_ratio(wav_path: Path, duration: float) -> float:
    """Fraction of the audio that is silence (< -35 dBFS for ≥ 0.5 s)."""
    cmd = [
        "ffmpeg", "-y", "-i", str(wav_path),
        "-af", "silencedetect=n=-35dB:d=0.5",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    total_silence = sum(
        float(m) for m in re.findall(r"silence_duration: ([\d.]+)", result.stderr)
    )
    return min(total_silence / max(duration, 1.0), 1.0)


def _measure_voice_energy_ratio(wav_path: Path) -> float:
    """Ratio of voice-band energy (80–3500 Hz) to full-band energy.

    Uses mean_volume (≈ RMS in dBFS) from ffmpeg volumedetect.
    A high ratio indicates speech-dominant content.
    """
    def _mean_db(extra_filters: str) -> float:
        af = (extra_filters + ",volumedetect") if extra_filters else "volumedetect"
        cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-af", af, "-f", "null", "-"]
        out = subprocess.run(cmd, capture_output=True, text=True)
        m = re.search(r"mean_volume: (-?[\d.]+) dB", out.stderr)
        return float(m.group(1)) if m else -91.0

    full_db  = _mean_db("")
    voice_db = _mean_db("highpass=f=80,lowpass=f=3500")
    # dB difference → linear amplitude ratio; clamp to [0, 1]
    return min(10 ** ((voice_db - full_db) / 20.0), 1.0)


def _measure_ebur128(wav_path: Path) -> tuple[float, float]:
    """Return (integrated_lufs, lra) from EBU R128 loudness analysis.

    integrated_lufs: overall loudness (low = quiet/ambient, high = music/loud)
    lra: loudness range (high = dynamic/speech, low = compressed/music)
    """
    cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-af", "ebur128", "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    lufs_m = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", stderr)
    lra_m  = re.search(r"LRA:\s+([\d.]+)\s+LU",   stderr)

    lufs = float(lufs_m.group(1)) if lufs_m else -70.0
    lra  = float(lra_m.group(1))  if lra_m  else 20.0
    return lufs, lra


def _speech_ratio_from_srt(srt_path: Path, duration: float) -> float:
    """Compute speech ratio from an existing SRT file (fast path)."""
    import srt as srt_lib
    subs = list(srt_lib.parse(srt_path.read_text()))
    if not subs:
        return 0.0
    speech_seconds = sum((s.end - s.start).total_seconds() for s in subs)
    return min(speech_seconds / max(duration, 1.0), 1.0)


def _speech_ratio_from_whisper(wav_path: Path, duration: float, model_size: str) -> float:
    """Run faster-whisper VAD on the first 60 s to estimate speech ratio."""
    from faster_whisper import WhisperModel

    probe_secs = min(60.0, duration)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", str(wav_path),
            "-t", str(probe_secs),
            "-ar", "16000", "-ac", "1",
            str(tmp_path),
        ], capture_output=True, check=True)

        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(
            str(tmp_path),
            language="zh",
            task="transcribe",
            vad_filter=True,
        )
        speech_seconds = sum(
            s.end - s.start for s in segments if s.no_speech_prob < 0.5
        )
        return min(speech_seconds / probe_secs, 1.0)
    finally:
        tmp_path.unlink(missing_ok=True)


# ── Decision rules ────────────────────────────────────────────────────────────

def _apply_rules(
    silence_ratio: float,
    voice_energy_ratio: float,
    speech_ratio: float,
    has_music: bool,
) -> VideoType:
    """
    Rule priority (highest to lowest):

    1. SILENT       — very high silence ratio (ASMR, ambient, cooking)
    2. NARRATION    — strong voice energy + confirmed speech (podcast, review, news)
    3. HYBRID       — music present + significant speech (vlog, music review)
    4. MUSIC_VISUAL — music dominant, minimal speech (dance, DIY, pets)
    5. NARRATION    — safe default
    """
    if silence_ratio > 0.80:
        return VideoType.SILENT

    if voice_energy_ratio > 0.35 and speech_ratio > 0.40:
        return VideoType.NARRATION

    if has_music and speech_ratio > 0.30:
        return VideoType.HYBRID

    if has_music:
        return VideoType.MUSIC_VISUAL

    return VideoType.NARRATION


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step2c_classify <output_dir> [model_size]")
        sys.exit(1)
    _model = sys.argv[2] if len(sys.argv) > 2 else "small"
    vt = classify(Path(sys.argv[1]), model_size=_model)
    print(f"Detected type: {vt.value}")
