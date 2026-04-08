
## Project Structure

The pipeline is organized with each step in its own folder for clean separation and easy expansion:

```
pipeline/
├── step1_download/          # Download Bilibili videos
├── step2_extract_audio/     # Audio extraction & normalization
├── step2b_separate_audio/   # Vocal/accompaniment separation
├── step3_transcribe/        # Speech-to-text (Whisper/Deepgram)
├── step4_translate/         # Caption translation (Gemini)
├── step5_tts/               # Text-to-speech generation
│   └── tts_providers/       # Pluggable TTS implementations
└── step6_compose/           # Final video composition
```

**Guidelines:**
- Each step is self-contained in its own folder
- Add helpers, configs, or utilities to the step's folder (don't scatter files)
- TTS providers stay in `pipeline/step5_tts/tts_providers/`
- Main entry points export from `main.py` in each step folder
- `main.py` files are imported by `pipeline.stepN` package (see `__init__.py`)

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health
