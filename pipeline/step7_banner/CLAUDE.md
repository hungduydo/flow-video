## Step 7 — Banner Generator

Generates platform-specific thumbnail/cover images using LLM-selected keyframes and Pillow composition.

### Entry point
```
banner(output_dir: Path, platform: str = "both", model: str = "gemini-3-flash-preview:cloud") -> Path
```
Returns path to `banner_youtube.jpg`.

### Outputs
| File | Description |
|------|-------------|
| `banner_youtube.jpg` | 1280×720 YouTube thumbnail |
| `banner_tiktok.jpg` | 1080×1920 TikTok cover image |
| `.step7.done` | Sentinel |

### How it works
1. **Frame extraction** (`frames.py`) — samples keyframes at scene midpoints (from `scenes.json`) + evenly-spaced positions across the middle 60% of the video. Scores by brightness, contrast, and colorfulness; returns top 5.
2. **LLM selection** (`main.py`) — sends top-5 frames as base64 JPEG images to Ollama Cloud (`gemini-3-flash-preview:cloud`). LLM picks the most dramatic frame and generates a 4-7 word Vietnamese hook title.
3. **Composition** (`compose.py`) — Pillow: smart-crop to platform size, bottom-heavy dark gradient, TikTok-red accent bar, bold outlined text.

### Design details
- YouTube: 1280×720, Impact font 88px
- TikTok: 1080×1920, Impact font 72px
- Accent bar color: `#FE2C55` (TikTok red)
- Gradient: 0% opacity at top → ~82% opacity at bottom

### Env vars
- `OLLAMA_API_KEY` — required for Ollama Cloud authentication
- `OLLAMA_URL` — optional override (default: `https://ollama.com`)

### CLI
```
python -m pipeline.step7_banner <output_dir> [--platform youtube|tiktok|both]
```
