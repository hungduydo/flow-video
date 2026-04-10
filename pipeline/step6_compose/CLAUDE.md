## Step 6 — Compose

Assembles the final video: watermark crop + dubbed audio + burned-in Vietnamese captions.

### Entry point
```
compose(output_dir, crf=23, platform="youtube", tiktok_crop_x=None, subtitle_position="bottom") -> Path
```
Returns path to the final video file.

### Outputs
| File | Description |
|------|-------------|
| `final_youtube.mp4` | 16:9 output (platform `youtube` or `both`) |
| `final_tiktok.mp4` | 9:16 cropped output (platform `tiktok` or `both`) |
| `final.mp4` | Copy of youtube output (backward compat) |
| `.step6.youtube.done` | Per-platform sentinel |
| `.step6.tiktok.done` | Per-platform sentinel |
| `.step6.done` | Legacy sentinel (backward compat) |

### ffmpeg pipeline (single pass)
1. **Zoom 5% + center crop** — scales to 105%, crops back to original dimensions, removing corner watermarks.
2. **Replace audio** — swaps original audio with `audio_vn_full.mp3`.
3. **Burn captions** — renders `captions_vn.srt` directly via ffmpeg `subtitles=` filter.

### Platform profiles
| Profile | Resolution | Caption style |
|---------|-----------|---------------|
| `youtube` | 16:9 (original) | White text on black box, bottom center |
| `tiktok` | 9:16 center crop | Larger bold text, higher position |
| `both` | Both of above | Produces two output files |

`--tiktok-crop-x` overrides the horizontal crop offset when the subject is off-center.

### Subtitle position
`subtitle_position` controls where captions appear:
- `"bottom"` (default) — bottom center (Alignment=2)
- `"top"` — top center (Alignment=8)
- `"auto"` — uses a vision LLM (Ollama) to detect where the source video has burned-in text, then places Vietnamese subtitles at the opposite region

### Auto-detection (`detect_subtitle.py`)
When `subtitle_position="auto"`, `detect_subtitle_region(video_path)` is called:
- Samples 5 frames from the middle 60% of the video
- Asks the LLM for a normalised `(x, y, width, height)` bounding box per frame
- Aggregates across detected frames: `min(x)`, `avg(y)`, `max(width)`, `avg(height)`
- Converts to pixels and pads 10 px on every side
- Returns `(x, y, w, h)` in pixels, or `None` if majority of frames had no detection
- `compose()` checks if the vertical centre of the box is in the top or bottom half,
  then places Vietnamese subtitles at the **opposite** region

Model defaults to `gemini-3-flash-preview:cloud` via Ollama Cloud (same as `step_remove_logo`).
API key: `OLLAMA_API_KEY` env var or `--ollama-api-key` flag.

### CLI
```
python -m pipeline.step6_compose <output_dir> [--crf N] [--platform youtube|tiktok|both]
    [--subtitle-position bottom|top|auto]
    [--ollama-url URL] [--model MODEL] [--ollama-api-key KEY] [--verbose]
```
