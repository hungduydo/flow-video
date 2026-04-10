## Step — Remove Logo

Detects and removes on-screen watermarks/logos from a video using LLM-based detection and ffmpeg `delogo` filter.

### Entry point
```
remove_logo(output_dir: Path) -> Path
```
Returns path to the processed video.

### Outputs
| File | Description |
|------|-------------|
| `original_nologo.mp4` | Video with logo removed |
| `.step_remove_logo.done` | Sentinel |

### How it works
1. **LLM detection** — samples frames and uses a vision LLM (Ollama) to locate the logo bounding box.
2. **ffmpeg delogo** — applies `delogo=x:y:w:h` filter to blur/remove the region.

### Edge cases handled
- Logo at `x=0` (left edge) — `delogo` requires `x >= 1`, so x is clamped to 1.
- Partial detection — if LLM returns incomplete coordinates, step is skipped gracefully.
- Expansion logic — detected box is expanded slightly to cover anti-aliased logo edges.

### CLI
```
python -m pipeline.step_remove_logo <output_dir>
```

### Notes
- This is an optional standalone step, not part of the main numbered pipeline sequence.
- Requires Ollama running locally with a vision-capable model.
