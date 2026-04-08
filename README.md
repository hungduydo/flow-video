# flow-video

Bilibili Re-Up Pipeline — Automatically convert Bilibili videos into re-dubbed Vietnamese videos with burned-in captions.

## Features

- **Download** Bilibili videos using yt-dlp
- **Audio Processing** Extract and separate vocals/accompaniment using Spleeter
- **Transcription** Convert Chinese speech to captions using faster-whisper or Deepgram
- **Translation** Translate captions to Vietnamese using Google Gemini 1.5 Flash
- **Text-to-Speech** Generate Vietnamese audio with edge-tts and sync to original timestamps
- **Composition** Create final video with watermark crop, Vietnamese dub, and burned-in captions

## Pipeline Overview

```
step1  Download video (yt-dlp)
       ↓
step2  Extract audio (ffmpeg → 16 kHz mono WAV)
       ↓
step2b Separate vocals/accompaniment (Spleeter 2stems)
       ↓
step3  Transcribe Chinese speech (faster-whisper or Deepgram → captions_cn.srt)
       ↓
step4  Translate to Vietnamese (Gemini 1.5 Flash → captions_vn.srt)
       ↓
step5  Generate Vietnamese TTS + sync to timestamps (edge-tts + atempo + amix)
       ↓
step6  Compose final video (ffmpeg: watermark crop + dub + captions)
```

## Requirements

### System Dependencies

- **ffmpeg** — Video and audio processing
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`
  - Windows: [FFmpeg builds](https://ffmpeg.org/download.html)

### Python Dependencies

```bash
pip install -r requirements.txt
```

Key packages:
- `yt-dlp` — Bilibili video download
- `faster-whisper` — Fast speech-to-text (Chinese)
- `deepgram-sdk` — Alternative transcription provider
- `demucs` — Audio source separation
- `google-generativeai` — Translation
- `edge-tts` — Vietnamese text-to-speech
- `python-dotenv` — Environment configuration

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd flow-video
   ```

2. Install system dependencies (ffmpeg)

3. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create `.env` file with API keys:
   ```bash
   cp .env.example .env  # If available, or create manually
   ```

   Required environment variables:
   - `GOOGLE_API_KEY` — Google Generative AI (for translation)
   - `DEEPGRAM_API_KEY` — Deepgram (optional, for transcription)

## Usage

### Basic Usage

```bash
python main.py https://www.bilibili.com/video/BV1234567890
```

### Options

```
--from-step N       Resume from step N (1–6), clears sentinels for N and later
--force             Re-run all steps (clears all sentinels)
--crf N             Output video quality, default 23 (lower = better, larger file)
--cookies FILE      Netscape cookie file for login-required Bilibili videos
--model SIZE        Whisper model size: large-v3 (default), medium, small
--transcriber NAME  Transcription provider: whisper (default) or deepgram
--output DIR        Base output directory, default ./output
```

### Examples

Resume from step 4 (translation):
```bash
python main.py https://www.bilibili.com/video/BV1234567890 --from-step 4
```

Use Deepgram for transcription with a smaller model:
```bash
python main.py https://www.bilibili.com/video/BV1234567890 --transcriber deepgram --model small
```

Set custom output directory and video quality:
```bash
python main.py https://www.bilibili.com/video/BV1234567890 --output ./videos --crf 28
```

## Output

Processing a video generates:
```
output/
├── <video_id>/
│   ├── metadata.json           # Video metadata (title, duration, etc.)
│   ├── captions_cn.srt         # Original Chinese captions
│   ├── captions_vn.srt         # Vietnamese captions
│   ├── audio_vn/
│   │   └── *.wav              # Vietnamese TTS audio segments
│   └── final_video.mp4         # Dubbed video with burned-in captions
```

## Architecture

The pipeline is organized into modular, self-contained steps:

```
pipeline/
├── step1_download/
│   ├── main.py           # Download video metadata and media
│   └── __init__.py
├── step2_extract_audio/
│   ├── main.py           # Audio extraction and normalization
│   └── __init__.py
├── step2b_separate_audio/
│   ├── main.py           # Vocal/accompaniment separation
│   └── __init__.py
├── step3_transcribe/
│   ├── main.py           # Speech-to-text transcription
│   └── __init__.py
├── step4_translate/
│   ├── main.py           # Caption translation
│   └── __init__.py
├── step5_tts/
│   ├── main.py           # Text-to-speech generation
│   ├── tts_providers/    # TTS provider implementations
│   │   ├── base.py
│   │   ├── edge_tts_provider.py
│   │   └── elevenlabs_provider.py
│   └── __init__.py
└── step6_compose/
    ├── main.py           # Final video composition
    └── __init__.py
```

Each step:
- Is isolated in its own folder with related utilities
- Uses sentinel files (`.stepN.done`) to track completion and enable resumable processing
- Can be extended with additional helpers or configs without affecting other steps

## Troubleshooting

### ffmpeg not found
Ensure ffmpeg is installed and in your PATH:
```bash
ffmpeg -version
```

### API key errors
Verify environment variables in `.env`:
```bash
echo $GOOGLE_API_KEY
echo $DEEPGRAM_API_KEY
```

### Transcription timeouts
For large videos, consider:
- Using smaller Whisper models (`--model small`)
- Switching to Deepgram (`--transcriber deepgram`)
- Resuming from step 3 if download/audio processing succeeds

### Out of memory
Audio separation (step2b) is memory-intensive. If you encounter memory issues:
- Close other applications
- Consider using a machine with more RAM
- Process videos sequentially

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Google Generative AI (required for translation)
GOOGLE_API_KEY=your_api_key_here

# Deepgram (optional, for alternative transcription)
DEEPGRAM_API_KEY=your_api_key_here

# Bilibili authentication (optional, for private videos)
BILIBILI_COOKIE_FILE=./cookies.txt
```

## License

[Specify your license here]

## Contributing

Contributions welcome! Please open an issue or pull request.

## Support

For issues, questions, or suggestions, please open an GitHub issue.
