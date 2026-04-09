"""
Workflow: Music & Visual (Group 1)

Videos where the music/sound is the main draw — Dance, Oddly Satisfying,
DIY, Pets. The original audio is preserved; only captions are translated.

Steps:
  step3   Transcribe any speech/captions → captions_cn.srt
            (uses audio.wav directly, skips step2b vocal separation)
  step4   Translate → captions_vn.srt
  step6m  Compose: zoom/crop watermark, burn translated captions,
            keep ORIGINAL audio stream (no TTS replacement)

Sentinel for compose: .step6m.done → final.mp4
"""

import argparse
import subprocess
from pathlib import Path

from pipeline.step3_transcribe import transcribe
from pipeline.step4_translate import translate

_FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
_FFMPEG_BIN  = str(_FFMPEG_FULL) if _FFMPEG_FULL.exists() else "ffmpeg"


def run(output_dir: Path, args: argparse.Namespace) -> Path:
    # step2b intentionally skipped — we keep the original mixed audio
    transcribe(output_dir, model_size=args.model, provider=args.transcriber)
    translate(output_dir, provider=args.translator)
    return compose_with_original_audio(output_dir, crf=args.crf)


def compose_with_original_audio(output_dir: Path, crf: int = 23) -> Path:
    """Compose final.mp4 keeping the original video audio stream.

    Same ffmpeg filter chain as step6_compose (zoom + captions) but maps
    audio from the original video (-map 0:a:0) instead of a separate dub file.
    Shared by silent_ambient workflow.
    """
    sentinel   = output_dir / ".step6m.done"
    video_path = output_dir / "original.mp4"
    srt_path   = output_dir / "captions_vn.srt"
    final_path = output_dir / "final.mp4"

    if sentinel.exists():
        print("[step6m] Skip — final.mp4 already composed (original-audio mode)")
        return final_path

    for p in (video_path, srt_path):
        if not p.exists():
            raise FileNotFoundError(f"Required file missing: {p}")

    print("[step6m] Composing final video (keeping original audio) …")
    print(f"         CRF={crf}, watermark zoom 5%, translated captions")

    srt_escaped = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")
    vf = (
        "scale=iw*1.05:ih*1.05,"
        "crop=iw/1.05:ih/1.05,"
        f"subtitles=filename={srt_escaped}"
        ":force_style='FontName=Arial,FontSize=16,"
        "PrimaryColour=&H00FFFFFF,"
        "BackColour=&H70000000,"
        "BorderStyle=4,Outline=0,Shadow=0,"
        "MarginV=20,"
        "Alignment=2'"
    )

    cmd = [
        _FFMPEG_BIN, "-y",
        "-i", str(video_path),
        "-map", "0:v:0",    # video from original.mp4
        "-map", "0:a:0",    # audio from original.mp4 (unchanged)
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(final_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg compose failed:\n{result.stderr}")

    sentinel.touch()
    size_mb = final_path.stat().st_size / 1_048_576
    print(f"[step6m] Done — {final_path} ({size_mb:.1f} MB)")
    return final_path
