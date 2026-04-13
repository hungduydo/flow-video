"""
Step 5a: Generate per-segment TTS audio from captions_vn.srt.

For each subtitle segment that contains speakable text, calls the TTS provider
and saves audio to audio_vn/seg_NNNN.mp3. Non-speakable segments are skipped
(step 5b will insert silence for them during assembly).

Output:
  output/{video_id}/audio_vn/seg_NNNN.mp3   (one file per speakable segment)
  output/{video_id}/.step5a.done             (sentinel)
"""

import re
import sys
from pathlib import Path

import srt
from tqdm import tqdm

from .tts_providers import TTSProvider, get_provider
from .utils import generate_silence

MIN_DURATION = 0.3   # seconds — skip TTS for extremely short segments


def _is_speakable(text: str) -> bool:
    """Return True if text contains at least one letter or digit.

    Punctuation-only strings (e.g. '...', '???', '!!!') cause edge-tts to
    return NoAudioReceived, so we skip them and insert silence instead.
    """
    return bool(re.search(r"[A-Za-z\d\u00C0-\u024F\u1E00-\u1EFF]", text))


def synth_segments(output_dir: Path, provider: str = "edge_tts") -> Path:
    """Generate TTS audio for each speakable subtitle segment.

    Already-generated segment files are skipped, so this is idempotent and
    can be re-run after a partial failure.

    Args:
        output_dir: pipeline output directory
        provider: TTS provider name ("edge_tts" or "elevenlabs")

    Returns:
        Path to audio_vn directory containing per-segment MP3 files.
    """
    output_dir = Path(output_dir).resolve()
    sentinel = output_dir / ".step5a.done"
    if sentinel.exists():
        print("[step5a] Skip — segments already synthesized")
        return output_dir / "audio_vn"

    vn_srt_path = output_dir / "captions_vn.srt"
    if not vn_srt_path.exists():
        raise FileNotFoundError(f"captions_vn.srt not found in {output_dir}")

    tts_provider: TTSProvider = get_provider(provider)
    fmt = tts_provider.audio_format

    audio_vn_dir = output_dir / "audio_vn"
    audio_vn_dir.mkdir(exist_ok=True)

    subtitles = list(srt.parse(vn_srt_path.read_text(encoding="utf-8")))
    print(f"[step5a] Synthesizing {len(subtitles)} segments (provider: {provider}) …")

    if provider == "elevenlabs":
        total_chars = sum(len(sub.content.strip()) for sub in subtitles)
        print(f"[step5a] ElevenLabs: ~{total_chars:,} characters to synthesize")

    for sub in tqdm(subtitles, desc="[step5a] TTS", unit="seg"):
        idx = f"{sub.index:04d}"
        text = sub.content.strip()
        original_duration = (sub.end - sub.start).total_seconds()
        seg_path = audio_vn_dir / f"seg_{idx}.mp3"

        if seg_path.exists():
            continue  # already done (re-run after partial failure)

        if not text or original_duration < MIN_DURATION or not _is_speakable(text):
            # Generate silence placeholder so step5b can detect non-speakable segments
            generate_silence(seg_path, max(original_duration, 0.1), fmt["sample_rate"], fmt["channels"])
            continue

        try:
            tts_provider.synth(text, seg_path)
        except Exception as exc:
            tqdm.write(f"[step5a] WARNING: TTS failed for seg {idx} ({text!r:.50}): {exc}; using silence")
            generate_silence(seg_path, original_duration, fmt["sample_rate"], fmt["channels"])

    sentinel.touch()
    print(f"[step5a] Done — {audio_vn_dir}")
    return audio_vn_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step5_tts.step5a_synth <output_dir> [provider]")
        sys.exit(1)
    _provider = sys.argv[2] if len(sys.argv) > 2 else "edge_tts"
    synth_segments(Path(sys.argv[1]), provider=_provider)
