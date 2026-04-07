"""
Step 1: Download a Bilibili video using yt-dlp.

Output:
  output/{video_id}/original.mp4
  output/{video_id}/metadata.json
  output/{video_id}/.step1.done  (sentinel)
"""

import json
import sys
from pathlib import Path

import yt_dlp


def download(url: str, output_base: Path, cookies_file: str | None = None) -> Path:
    # ── 1. Probe video info (no download) to get the video ID ──────────────
    probe_opts: dict = {"quiet": True, "no_warnings": True, "skip_download": True}
    if cookies_file:
        probe_opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    video_id: str = info["id"]
    output_dir = output_base / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 2. Sentinel check ───────────────────────────────────────────────────
    sentinel = output_dir / ".step1.done"
    if sentinel.exists():
        print(f"[step1] Skip — already downloaded ({video_id})")
        return output_dir

    # ── 3. Download best quality mp4 ────────────────────────────────────────
    print(f"[step1] Downloading {video_id} …")
    dl_opts: dict = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_dir / "original.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
    }
    if cookies_file:
        dl_opts["cookiefile"] = cookies_file

    with yt_dlp.YoutubeDL(dl_opts) as ydl:
        ydl.download([url])

    # ── 4. Save metadata ─────────────────────────────────────────────────────
    metadata = {
        "id": video_id,
        "title": info.get("title", ""),
        "duration": info.get("duration", 0),
        "url": url,
        "uploader": info.get("uploader", ""),
        "webpage_url": info.get("webpage_url", url),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sentinel.touch()
    print(f"[step1] Done — {output_dir}")
    return output_dir


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m pipeline.step1_download <url> [output_base]")
        sys.exit(1)
    _url = sys.argv[1]
    _base = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("output")
    download(_url, _base)
