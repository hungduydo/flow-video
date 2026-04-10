
## Project Structure

The pipeline is organized with each step in its own folder for clean separation and easy expansion:

```
pipeline/
├── step1_download/          # Download Bilibili videos
├── step1b_scenes/           # Scene cut detection → scenes.json
├── step2_extract_audio/     # Audio extraction & normalization
├── step2b_separate_audio/   # Vocal/accompaniment separation
├── step3_transcribe/        # Speech-to-text (Whisper/Deepgram) + noise cleanup
├── step4_translate/         # Caption translation (Gemini or Claude)
│   └── providers/           # Pluggable translation implementations (gemini.py, claude.py)
├── step5_tts/               # Text-to-speech generation
│   └── tts_providers/       # Pluggable TTS implementations
├── step6_compose/           # Final video composition
└── step_remove_logo/        # Optional: LLM-based watermark removal
```

**Guidelines:**
- Each step is self-contained in its own folder
- Add helpers, configs, or utilities to the step's folder (don't scatter files)
- Translation providers stay in `pipeline/step4_translate/providers/`
- TTS providers stay in `pipeline/step5_tts/tts_providers/`
- Main entry points export from `main.py` in each step folder
- Every step has a `__main__.py` so it can be run with `python -m pipeline.stepN`
- `main.py` files are imported by `pipeline.stepN` package (see `__init__.py`)

## Step 1b — Scene detection

`step1b_scenes/main.py` runs between step1 and step2:
- Primary: `ffmpeg scdet` filter — always available, no extra deps.
- Fallback: PySceneDetect `AdaptiveDetector` if ffmpeg yields 0 cuts (`pip install "scenedetect>=0.6,<1.0"`).
- Output: `scenes.json` — `{"cuts": [...], "scenes": [...], "detector": "...", "video_duration": N}`.
- `scenes.json` is **optional** — all downstream steps work unchanged if it's absent.

Downstream consumers:
- **step4**: embeds cut timestamps into `system_prompt` for concise translation near boundaries.
- **step5**: enforces gap silence at cut boundaries; trims TTS that spans a cut, padding remainder with silence to preserve A/V sync.

## Step 4 — Translation architecture

`step4_translate/` is split into focused files:
- `main.py` — `translate(output_dir, provider)` entry point only
- `prompt.py` — shared `SYSTEM_PROMPT`
- `utils.py` — `batch()`, `parse_json_response()`, `build_prompt()`, `clean_subtitles()`
- `providers/gemini.py` — Gemini 2.0 Flash provider (`run(subtitles, system_prompt)`)
- `providers/claude.py` — Claude Sonnet 4.6 provider (`run(subtitles, system_prompt)`)

Both providers use the same interface: batched translation with 3-segment context overlap and JSON array output. Adding a new provider = create `providers/yourprovider.py` with a `run()` function.

## Step 3 — Noise cleanup

After transcription, `_clean_subtitles()` drops segments with fewer than 2 CJK characters (single-char Whisper fragments like `研`, `究`, `了`, and punct-only segments like `。`). This runs in both Whisper and Deepgram paths before writing `captions_cn.srt`.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

