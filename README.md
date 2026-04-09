# flow-video

Bilibili Re-Up Pipeline — Automatically convert Bilibili videos into re-dubbed Vietnamese videos with burned-in captions.

## Features

- **Download** Bilibili videos using yt-dlp
- **Logo Removal** Auto-detect and remove persistent corner watermarks from any video source
- **Audio Processing** Extract and separate vocals/accompaniment using Demucs
- **Transcription** Convert Chinese speech to captions using faster-whisper or Deepgram, with automatic noise cleanup
- **Translation** Translate captions to Vietnamese using Gemini 2.0 Flash or Claude Sonnet 4.6
- **Text-to-Speech** Generate Vietnamese audio with edge-tts or ElevenLabs, synced to original timestamps
- **Composition** Create final video with Vietnamese dub and burned-in captions (YouTube 16:9 or TikTok 9:16)

## Pipeline Overview

```
step1   Download video (yt-dlp)
        ↓
step2   Extract audio (ffmpeg → 16 kHz mono WAV)
        ↓
step2b  Separate vocals/accompaniment (Demucs 2stems)
        ↓
step3   Transcribe Chinese speech → captions_cn.srt
        (faster-whisper or Deepgram, with noise fragment cleanup)
        ↓
step4   Translate to Vietnamese → captions_vn.srt
        (Gemini 2.0 Flash or Claude Sonnet 4.6)
        ↓
step5   Generate Vietnamese TTS + sync to timestamps
        (edge-tts or ElevenLabs + atempo + amix with accompaniment)
        ↓
step6   Compose final video
        (ffmpeg: dub + burned-in captions, YouTube or TikTok crop)
```

## Requirements

### System Dependencies

- **ffmpeg** — Video and audio processing
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`

### Python Dependencies

```bash
pip install -r requirements.txt
```

Key packages:
- `yt-dlp` — Bilibili video download
- `faster-whisper` — Local speech-to-text (Chinese)
- `deepgram-sdk` — Cloud transcription provider
- `demucs` — Audio source separation
- `google-generativeai` — Gemini translation
- `anthropic` — Claude translation
- `edge-tts` — Vietnamese text-to-speech
- `python-dotenv` — Environment configuration

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd flow-video
   ```

2. Install ffmpeg (see above)

3. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create `.env` with your API keys:
   ```env
   # Required for Gemini translation (default)
   GEMINI_API_KEY=your_key_here

   # Required for Claude translation (--translator claude)
   ANTHROPIC_API_KEY=your_key_here

   # Required for Deepgram transcription (--transcriber deepgram)
   DEEPGRAM_API_KEY=your_key_here

   # Required for ElevenLabs TTS (--tts-provider elevenlabs)
   ELEVENLABS_API_KEY=your_key_here
   ```

## Usage

### Full Pipeline (Interactive)

Running without flags prompts you to choose all options interactively:

```bash
python main.py https://www.bilibili.com/video/BV1234567890
```

### Full Pipeline (Non-Interactive)

```bash
python main.py <url> \
  --transcriber whisper \
  --translator gemini \
  --tts-provider edge_tts \
  --platform youtube
```

### Options

```
--transcriber NAME   Transcription provider: whisper (default) or deepgram
--model SIZE         Whisper model: large-v3 (default), large-v2, medium, small, base
--translator NAME    Translation provider: gemini (default) or claude
--tts-provider NAME  TTS provider: edge_tts (default) or elevenlabs
--platform NAME      Output format: youtube (default), tiktok, or both
--tiktok-crop-x N    Horizontal crop offset for TikTok 9:16 (default: center)
--from-step N        Resume from step N (1–6), clears sentinels for N and later
--force              Re-run all steps (clears all sentinels)
--crf N              Video quality, default 23 (lower = better quality, larger file)
--cookies FILE       Netscape cookie file for login-required Bilibili videos
--output DIR         Base output directory, default ./output
```

### Run Individual Steps

Every step can be run standalone with `-m`:

```bash
python -m pipeline.step3_transcribe output/BV1234567890 --transcriber whisper
python -m pipeline.step4_translate  output/BV1234567890 --provider claude
python -m pipeline.step5_tts        output/BV1234567890 --provider edge_tts
python -m pipeline.step6_compose    output/BV1234567890 --platform tiktok
```

To re-run a step, delete its sentinel first:

```bash
rm output/BV1234567890/.step4.done
python -m pipeline.step4_translate output/BV1234567890 --provider claude
```

### Examples

Use Claude for higher-quality translation:
```bash
python main.py <url> --translator claude
```

Use Deepgram (fast cloud transcription) with Claude translation:
```bash
python main.py <url> --transcriber deepgram --translator claude
```

Export for both YouTube and TikTok:
```bash
python main.py <url> --platform both --tiktok-crop-x 400
```

Resume from translation step:
```bash
python main.py <url> --from-step 4
```

## Output

```
output/
└── <video_id>/
    ├── metadata.json           # Video title, duration, URL
    ├── original.mp4            # Downloaded video
    ├── audio.wav               # Extracted audio (16 kHz mono)
    ├── vocals.wav              # Separated vocals
    ├── accompaniment.mp3       # Separated background music
    ├── captions_cn.srt         # Chinese captions (noise-cleaned)
    ├── captions_vn.srt         # Vietnamese captions
    ├── audio_vn_full.mp3       # Vietnamese dub mixed with accompaniment
    ├── final_youtube.mp4       # Final 16:9 video
    └── final_tiktok.mp4        # Final 9:16 video (if --platform tiktok/both)
```

## Logo / Watermark Removal

A standalone tool that auto-detects and removes persistent corner logos from any video source (Bilibili, YouTube, news channels, etc.).

### How it works

1. **Detection** — Samples 30 frames and computes per-pixel standard deviation across the four corner regions. Static watermarks have very low variance (consistent pixels) while moving content has high variance. The corner with the most static pixels above a threshold is selected.

2. **Removal** — Two quality modes:
   - `fast` (default) — ffmpeg `delogo` filter, real-time speed, slight interpolation at edges
   - `high` — OpenCV TELEA inpainting per frame, clean/natural result, ~3–5 min per 5-min video

### Usage

```bash
# Basic — outputs {stem}_clean.mp4 next to input
python -m pipeline.step_remove_logo input.mp4

# Custom output path
python -m pipeline.step_remove_logo input.mp4 output_clean.mp4

# High quality inpainting
python -m pipeline.step_remove_logo input.mp4 --quality high

# Detect only (no processing)
python -m pipeline.step_remove_logo input.mp4 --detect-only
```

### Example output

```
[remove_logo] Detecting watermark in original.mp4 …
[remove_logo] Detected: bottom_right at x=1556 y=983 w=330 h=63
[remove_logo] Removing with mode='fast' …
[remove_logo] Done → original_clean.mp4 (206.5 MB)
```

If no static watermark is found the input is copied unchanged.

### Programmatic usage

```python
from pipeline.step_remove_logo import remove_logo, detect_watermark_region

# Returns (corner_name, x, y, w, h) or None
region = detect_watermark_region("input.mp4")

# Returns Path to output file
out = remove_logo("input.mp4", "clean.mp4", quality="fast")
```

---

## Architecture

```
pipeline/
├── step1_download/
│   ├── __main__.py
│   ├── main.py
│   └── __init__.py
├── step2_extract_audio/
│   ├── __main__.py
│   ├── main.py
│   └── __init__.py
├── step2b_separate_audio/
│   ├── __main__.py
│   ├── main.py
│   └── __init__.py
├── step3_transcribe/
│   ├── __main__.py
│   ├── main.py           # Whisper + Deepgram + _clean_subtitles()
│   └── __init__.py
├── step4_translate/
│   ├── __main__.py
│   ├── main.py           # Entry point: translate(output_dir, provider)
│   ├── prompt.py         # Shared SYSTEM_PROMPT
│   ├── utils.py          # batch(), parse_json_response(), build_prompt(), clean_subtitles()
│   ├── providers/
│   │   ├── gemini.py     # Gemini 2.0 Flash provider
│   │   └── claude.py     # Claude Sonnet 4.6 provider
│   └── __init__.py
├── step5_tts/
│   ├── __main__.py
│   ├── main.py
│   ├── tts_providers/
│   │   ├── edge_tts_provider.py
│   │   └── elevenlabs_provider.py
│   └── __init__.py
├── step6_compose/
│   ├── __main__.py
│   ├── main.py
│   └── __init__.py
└── step_remove_logo/
    ├── __main__.py
    ├── main.py           # detect_watermark_region(), remove_logo()
    └── __init__.py
```

### Translation Provider Design

Both providers share the same interface:
- Batches of ≤50 segments / ≤4,000 source chars
- Last 3 segments passed as read-only context for cross-batch coherence
- JSON array output — no fragile line-count matching
- Video title from `metadata.json` injected for domain vocabulary

To add a new translation provider, create `providers/yourprovider.py` with:
```python
def run(subtitles: list[srt.Subtitle], system_prompt: str) -> list[str]: ...
```
Then add it to the `provider` choices in `main.py` and `__main__.py`.

## Troubleshooting

### ffmpeg not found
```bash
ffmpeg -version
```
If missing, install via brew/apt (see Requirements).

### API key errors
Check your `.env` file has the right key for the provider you selected:
- Gemini → `GEMINI_API_KEY`
- Claude → `ANTHROPIC_API_KEY`
- Deepgram → `DEEPGRAM_API_KEY`
- ElevenLabs → `ELEVENLABS_API_KEY`

### Transcription has single-character noise
Step 3 now automatically removes single-character fragments and punct-only segments produced by Whisper. If you have old `captions_cn.srt` files with noise, re-run from step 3:
```bash
python main.py <url> --from-step 3
```

### Out of memory (step 2b)
Audio separation with Demucs is memory-intensive. Close other applications or process videos sequentially.

### Large video / slow transcription
- Use a smaller Whisper model: `--model small`
- Switch to Deepgram for fast cloud transcription: `--transcriber deepgram`
