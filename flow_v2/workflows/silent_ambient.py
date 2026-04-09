"""
Workflow: Silent / Ambient (Group 3)

Videos where ambient sound is the main experience — ASMR, Cooking (healing
style), Woodworking, Camping. The original audio is completely preserved;
only translated captions are added to convey context or recipes.

Steps:
  step3   Transcribe any commentary → captions_cn.srt
            (uses audio.wav directly; low speech content is fine)
  step4   Translate → captions_vn.srt
  step6m  Compose: zoom/crop watermark, burn translated captions,
            keep ORIGINAL audio (ambient sounds untouched)

Mechanics are identical to music_visual — shares compose_with_original_audio.
"""

import argparse
from pathlib import Path

from pipeline.step3_transcribe import transcribe
from pipeline.step4_translate import translate
from .music_visual import compose_with_original_audio


def run(output_dir: Path, args: argparse.Namespace) -> Path:
    # step2b intentionally skipped — ambient sounds must not be separated
    transcribe(output_dir, model_size=args.model, provider=args.transcriber)
    translate(output_dir, provider=args.translator)
    return compose_with_original_audio(output_dir, crf=args.crf)
