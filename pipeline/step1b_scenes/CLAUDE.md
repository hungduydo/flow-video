## Step 1b — Scene Detection

Detects visual scene cuts in the source video and writes `scenes.json`. Run between step1 and step2.

### Entry point
```
detect_scenes(output_dir: Path) -> Path
```
Returns path to `scenes.json`.

### Outputs
| File | Description |
|------|-------------|
| `scenes.json` | Cut timestamps, scene intervals, detector name, video duration |
| `.step1b.done` | Sentinel — skips re-detection on re-run |

### scenes.json format
```json
{
  "cuts": [12.34, 45.67, ...],
  "scenes": [[0.0, 12.34], [12.34, 45.67], ...],
  "detector": "ffmpeg_scdet",
  "video_duration": 123.45
}
```

### Detection strategy
1. **Primary** — `ffmpeg scdet` filter (`threshold=10`, `sc_pass=1`). Parses `lavfi.scd.time:` lines from stderr. Always available.
2. **Fallback** — `PySceneDetect AdaptiveDetector` if ffmpeg yields 0 cuts. Requires optional install: `pip install "scenedetect>=0.6,<1.0"`.

### Helper functions
| Function | Description |
|----------|-------------|
| `_get_video_duration(video_path)` | ffprobe duration, returns `0.0` on failure |
| `_cuts_to_scenes(cuts, duration)` | Converts cut list → `[(start, end), ...]` |
| `_detect_with_ffmpeg(video_path)` | Primary detector |
| `_detect_with_pyscenedetect(video_path)` | Fallback detector |

### Downstream consumers
- **step4_translate** — embeds cut timestamps into system prompt for concise translation near boundaries.
- **step5_tts** — inserts silence at cut boundaries; trims TTS that crosses a cut.

`scenes.json` is always **optional** — if absent, all downstream steps behave exactly as before.

### CLI
```
python -m pipeline.step1b_scenes <output_dir>
```

### Sentinel clearing
Cleared when `--force` or `--from-step 1`/`--from-step 2` is used in `main.py` / `flow_v2/main_v2.py`.
