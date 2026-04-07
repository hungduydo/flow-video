"""
Step 3: Transcribe Chinese audio → captions_cn.srt.

Two providers, selectable via the `provider` argument:

  whisper   (default) — faster-whisper large-v3, runs locally, no API key needed.
                        First run downloads ~3 GB model. Slow on CPU.

  deepgram  — Deepgram Nova-2, cloud API, results in seconds.
              Requires DEEPGRAM_API_KEY in .env.

Both paths produce the same output format: captions_cn.srt + .step3.done sentinel.

IMPORTANT:
  task="transcribe"  → Chinese text output (NOT English translation)
  language="zh"      → forced, never autodetect on Bilibili content

Output:
  output/{video_id}/captions_cn.srt
  output/{video_id}/.step3.done  (sentinel)
"""

import os
import sys
from datetime import timedelta
from pathlib import Path

import srt
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()


def _seconds_to_timedelta(seconds: float) -> timedelta:
    return timedelta(seconds=seconds)


# ── Whisper provider ──────────────────────────────────────────────────────────

MUSIC_PROB_THRESHOLD = 0.6  # segments with no_speech_prob above this are skipped


def _transcribe_whisper(output_dir: Path, srt_path: Path, sentinel: Path, model_size: str) -> Path:
    from faster_whisper import WhisperModel

    print(f"[step3] Loading faster-whisper model '{model_size}' …")
    print("        (first run downloads ~3 GB for large-v3 — be patient)")
    model = WhisperModel(model_size, device="auto", compute_type="auto")

    wav_path = output_dir / "vocals.wav"
    if not wav_path.exists():
        wav_path = output_dir / "audio.wav"
    print(f"[step3] Transcribing (Chinese, whisper) using {wav_path.name} …")
    segments, info = model.transcribe(
        str(wav_path),
        language="zh",
        task="transcribe",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    print(f"        Detected language: {info.language} ({info.language_probability:.1%})")

    subtitles: list[srt.Subtitle] = []
    skipped_music = 0
    idx = 1

    for seg in tqdm(segments, desc="[step3] segments", unit="seg"):
        if seg.no_speech_prob > MUSIC_PROB_THRESHOLD:
            skipped_music += 1
            continue
        subtitles.append(
            srt.Subtitle(
                index=idx,
                start=_seconds_to_timedelta(seg.start),
                end=_seconds_to_timedelta(seg.end),
                content=seg.text.strip(),
            )
        )
        idx += 1

    if skipped_music:
        print(f"        Skipped {skipped_music} non-speech segment(s) (music/noise)")

    srt_path.write_text(srt.compose(subtitles), encoding="utf-8")
    sentinel.touch()
    print(f"[step3] Done — {len(subtitles)} segments → {srt_path}")
    return srt_path


# ── Deepgram provider ─────────────────────────────────────────────────────────

DEEPGRAM_CONFIDENCE_THRESHOLD = 0.5  # utterances below this are skipped


def _transcribe_deepgram(output_dir: Path, srt_path: Path, sentinel: Path) -> Path:
    from deepgram import DeepgramClient

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise EnvironmentError("DEEPGRAM_API_KEY not set — add it to .env")

    wav_path = output_dir / "vocals.wav"
    if not wav_path.exists():
        wav_path = output_dir / "audio.wav"
    print(f"[step3] Transcribing (Chinese, Deepgram Nova-2) using {wav_path.name} …")

    dg = DeepgramClient(api_key=api_key)
    audio_bytes = wav_path.read_bytes()
    response = dg.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model="nova-2",
        language="zh",
        utterances=True,
        punctuate=True,
    )

    utterances = response.results.utterances or []
    subtitles: list[srt.Subtitle] = []
    skipped = 0
    idx = 1

    for utt in utterances:
        if utt.confidence < DEEPGRAM_CONFIDENCE_THRESHOLD:
            skipped += 1
            continue
        subtitles.append(
            srt.Subtitle(
                index=idx,
                start=_seconds_to_timedelta(utt.start),
                end=_seconds_to_timedelta(utt.end),
                content=utt.transcript.strip(),
            )
        )
        idx += 1

    if skipped:
        print(f"        Skipped {skipped} low-confidence utterance(s)")

    srt_path.write_text(srt.compose(subtitles), encoding="utf-8")
    sentinel.touch()
    print(f"[step3] Done — {len(subtitles)} segments → {srt_path}")
    return srt_path


# ── Public entry point ────────────────────────────────────────────────────────

def transcribe(output_dir: Path, model_size: str = "large-v3", provider: str = "whisper") -> Path:
    sentinel = output_dir / ".step3.done"
    if sentinel.exists():
        print("[step3] Skip — captions_cn.srt already exists")
        return output_dir / "captions_cn.srt"

    wav_path = output_dir / "vocals.wav" if (output_dir / "vocals.wav").exists() else output_dir / "audio.wav"
    if not wav_path.exists():
        raise FileNotFoundError(f"Neither vocals.wav nor audio.wav found in {output_dir}")

    srt_path = output_dir / "captions_cn.srt"

    if provider == "deepgram":
        return _transcribe_deepgram(output_dir, srt_path, sentinel)
    else:
        return _transcribe_whisper(output_dir, srt_path, sentinel, model_size)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("output_dir")
    p.add_argument("--model", default="large-v3")
    p.add_argument("--transcriber", choices=["whisper", "deepgram"], default="whisper")
    a = p.parse_args()
    transcribe(Path(a.output_dir), model_size=a.model, provider=a.transcriber)
