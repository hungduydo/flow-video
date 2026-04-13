"""
Step 5: Vietnamese captions_vn.srt → per-segment TTS audio → audio_vn_full.mp3

Split into two sub-steps:
  5a (synth)    — call TTS provider for each subtitle segment → audio_vn/seg_NNNN.mp3
  5b (assemble) — calculate gaps, fit to slots, concatenate, speed-adjust, mix

Running step 5a and 5b separately lets you re-run assembly (gap tuning, speed
adjust) without paying TTS API costs again.

Output:
  output/{video_id}/audio_vn/seg_NNNN.mp3          (step 5a: per-segment TTS)
  output/{video_id}/audio_vn_speech.mp3             (step 5b: concatenated)
  output/{video_id}/audio_vn_speech_adjusted.mp3    (step 5b: after speed adjust)
  output/{video_id}/audio_vn_full.mp3               (step 5b: final + accompaniment)
  output/{video_id}/.step5a.done                    (step 5a sentinel)
  output/{video_id}/.step5b.done                    (step 5b sentinel)
  output/{video_id}/.step5.done                     (combined sentinel, backward compat)
"""

import sys
from pathlib import Path

from .step5a_synth import synth_segments
from .step5b_assemble import assemble_audio


def generate_tts(output_dir: Path, provider: str = "edge_tts") -> Path:
    """Run step 5a (synth) then step 5b (assemble).

    Args:
        output_dir: pipeline output directory
        provider: TTS provider name ("edge_tts" or "elevenlabs")

    Returns:
        Path to audio_vn_full.mp3
    """
    output_dir = Path(output_dir).resolve()

    # Fast-path: both sub-steps already done
    if (output_dir / ".step5.done").exists():
        print("[step5] Skip — audio_vn_full.mp3 already generated")
        return output_dir / "audio_vn_full.mp3"

    synth_segments(output_dir, provider=provider)
    full_audio = assemble_audio(output_dir)

    # Combined sentinel for backward compatibility with --from-step logic
    (output_dir / ".step5.done").touch()
    return full_audio


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step5_tts <output_dir> [provider]")
        sys.exit(1)
    _provider = sys.argv[2] if len(sys.argv) > 2 else "edge_tts"
    generate_tts(Path(sys.argv[1]), provider=_provider)
