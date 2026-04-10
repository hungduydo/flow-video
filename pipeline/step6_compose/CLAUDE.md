## Step 6 — Compose

Assembles the final video: watermark crop + dubbed audio + burned-in Vietnamese captions.

### Entry point
```
compose(output_dir: Path, crf: int = 23, platform: str = "youtube", tiktok_crop_x: int | None = None) -> Path
```
Returns path to the final video file.

### Outputs
| File | Description |
|------|-------------|
| `captions_vn_{platform}.ass` | Intermediate ASS subtitle file (kept for debugging) |
| `final_youtube.mp4` | 16:9 output (platform `youtube` or `both`) |
| `final_tiktok.mp4` | 9:16 cropped output (platform `tiktok` or `both`) |
| `final.mp4` | Copy of youtube output (backward compat) |
| `.step6.youtube.done` | Per-platform sentinel |
| `.step6.tiktok.done` | Per-platform sentinel |
| `.step6.done` | Legacy sentinel (backward compat) |

### ffmpeg pipeline (single pass)
1. **Zoom 5% + center crop** — scales to 105%, crops back to original dimensions, removing corner watermarks.
2. **Replace audio** — swaps original audio with `audio_vn_full.mp3`.
3. **Burn captions** — renders ASS subtitles directly into video frames.

### Platform profiles
| Profile | Resolution | Caption style |
|---------|-----------|---------------|
| `youtube` | 16:9 (original) | White text on black box, bottom center |
| `tiktok` | 9:16 center crop | Larger bold text, higher position |
| `both` | Both of above | Produces two output files |

`--tiktok-crop-x` overrides the horizontal crop offset when the subject is off-center.

### CLI
```
python -m pipeline.step6_compose <output_dir> [--crf N] [--platform youtube|tiktok|both]
```
