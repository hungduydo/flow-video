"""
Workflow: Narration / Hybrid (Groups 2 & 5)

Full voice-replacement pipeline — identical to the original main.py flow.
Used for: Story, Podcast, News, Facts, Vlog, Review (with background music).

Steps:
  step2b  Separate vocals / accompaniment (Demucs)
  step3   Transcribe speech → captions_cn.srt
  step4   Translate → captions_vn.srt
  step5   Generate Vietnamese TTS + mix
  step6   Compose final video (replace audio, burn captions, zoom crop)
"""

import argparse
from pathlib import Path

from pipeline.step2b_separate_audio import separate_audio
from pipeline.step3_transcribe import transcribe
from pipeline.step4_translate import translate
from pipeline.step5_tts import generate_tts
from pipeline.step6_compose import compose


def run(output_dir: Path, args: argparse.Namespace) -> Path:
    separate_audio(output_dir)
    transcribe(output_dir, model_size=args.model, provider=args.transcriber)
    translate(output_dir, provider=args.translator)
    generate_tts(output_dir, provider=args.tts_provider)
    return compose(output_dir, crf=args.crf, platform=args.platform, tiktok_crop_x=args.tiktok_crop_x)
