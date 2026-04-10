## Step 1 — Download

Downloads a Bilibili (or any yt-dlp-supported) video into `output/{video_id}/`.

### Entry point
```
download(url: str, output_base: Path, cookies_file: str | None = None) -> Path
```
Returns `output_dir` (e.g. `output/BV1xx411c7mD/`).

### Outputs
| File | Description |
|------|-------------|
| `original.mp4` | Best-quality merged video |
| `metadata.json` | `id`, `title`, `duration`, `url`, `uploader`, `webpage_url` |
| `.step1.done` | Sentinel — skips re-download on re-run |

### How it works
1. **Probe** (`skip_download=True`) to resolve `video_id` and fill `metadata.json` — always runs, even if sentinel exists, because `output_dir` depends on it.
2. **Sentinel check** — if `.step1.done` exists, returns `output_dir` immediately.
3. **Download** best `mp4+m4a` via yt-dlp, merge to `original.mp4`.
4. Write `metadata.json`, touch sentinel.

### CLI
```
python -m pipeline.step1_download <url> [output_base]
```

### Notes
- `cookies_file` is a Netscape-format cookie file for login-restricted videos.
- The probe step is intentionally not sentinel-guarded — it's fast and `output_dir` must be resolved before any sentinel logic can run.
