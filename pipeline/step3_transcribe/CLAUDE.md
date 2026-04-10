## Step 3 — Transcribe

Transcribes Chinese speech to `captions_cn.srt`. Two pluggable providers.

### Entry point
```
transcribe(output_dir: Path, model_size: str = "large-v3", provider: str = "whisper") -> Path
```
Returns path to `captions_cn.srt`.

### Outputs
| File | Description |
|------|-------------|
| `captions_cn.srt` | Chinese subtitles, noise-cleaned |
| `.step3.done` | Sentinel |

### Providers
| Provider | Notes |
|----------|-------|
| `whisper` (default) | `faster-whisper` large-v3 locally. ~3 GB model download on first run. `task="transcribe"`, `language="zh"` forced. |
| `deepgram` | Cloud API, results in seconds. Requires `DEEPGRAM_API_KEY` in `.env`. |

### Noise cleanup (`_clean_subtitles`)
Drops segments with fewer than 2 CJK characters — removes single-character Whisper fragments (`研`, `究`) and punctuation-only segments (`。`). Runs in both provider paths before writing the SRT.

### CLI
```
python -m pipeline.step3_transcribe <output_dir> [whisper|deepgram] [model_size]
```

### Notes
- Always use `task="transcribe"` not `"translate"` — Whisper's translate mode produces English, not Chinese.
- `language="zh"` is forced; never autodetect on Bilibili content.
- Input prefers `vocals.wav` (from step2b) over `audio.wav` when available.
