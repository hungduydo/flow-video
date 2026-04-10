"""
Step 7: Generate video banner thumbnails.

Pipeline:
  1. Extract candidate keyframes from final_youtube.mp4 (OpenCV + scenes.json)
  2. Score frames by brightness, contrast, colorfulness
  3. Ask Ollama Cloud (gemini-3-flash-preview:cloud) to pick best frame
     and generate a punchy Vietnamese hook title
  4. Compose banners with gradient overlay + bold text (Pillow)

Outputs:
  banner_youtube.jpg    1280×720  YouTube thumbnail
  banner_tiktok.jpg     1080×1920 TikTok cover image
  .step7.done           Sentinel
"""

import json
import os
from pathlib import Path

from .compose import compose_banner
from .frames import _frame_to_b64, extract_candidates

_DEFAULT_MODEL = "gemini-3-flash-preview:cloud"
_DEFAULT_OLLAMA_URL = "https://ollama.com"

_SYSTEM_PROMPT = """\
You are a YouTube/TikTok thumbnail expert. Given candidate video frames and context:
1. Pick the single most visually dramatic, eye-catching frame (high contrast, clear subject, dynamic action).
2. Write a punchy 4-7 word Vietnamese hook title that creates curiosity or urgency.

Reply with ONLY valid JSON — no markdown, no explanation:
{"frame": <integer 0 to N-1>, "title": "<Vietnamese title>"}"""


def _call_llm(
    frames: list,
    srt_context: str,
    video_title: str,
    model: str,
    ollama_url: str,
    api_key: str | None,
) -> tuple[int, str]:
    """Send frames to Ollama Cloud; return (chosen_frame_index, hook_title)."""
    from ollama import Client

    resolved_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
    client = Client(
        host=ollama_url,
        headers={"Authorization": f"Bearer {resolved_key}"} if resolved_key else {},
    )

    b64_images = [_frame_to_b64(f) for f in frames]
    n = len(b64_images)

    user_text = (
        f"Video title: {video_title}\n\n"
        f"Caption excerpt:\n{srt_context}\n\n"
        f"I am sending {n} candidate frames (index 0 to {n - 1}). "
        "Select the best one and return the required JSON."
    )

    response = client.chat(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_text, "images": b64_images},
        ],
        format="json",
        stream=False,
    )

    content = response.message.content if hasattr(response, "message") else ""
    content = content.strip()
    # Strip markdown code fences if the model added them
    if content.startswith("```"):
        parts = content.split("```")
        content = parts[1].lstrip("json").strip() if len(parts) > 1 else content

    data = json.loads(content)
    frame_idx = max(0, min(int(data.get("frame", 0)), n - 1))
    title = str(data.get("title", video_title or "Video Hay Nhất")).strip()
    return frame_idx, title


def banner(
    output_dir: Path,
    platform: str = "both",
    model: str = _DEFAULT_MODEL,
    ollama_url: str | None = None,
    api_key: str | None = None,
) -> Path:
    """Generate banner thumbnail(s) for the given pipeline output directory.

    Args:
        output_dir: Pipeline output directory (contains final_youtube.mp4, etc.)
        platform:   'youtube', 'tiktok', or 'both'
        model:      Ollama model name for LLM frame selection
        ollama_url: Ollama Cloud base URL (default: https://ollama.com)
        api_key:    Ollama API key (falls back to OLLAMA_API_KEY env var)

    Returns:
        Path to banner_youtube.jpg (or banner_tiktok.jpg when platform='tiktok').
    """
    sentinel = output_dir / ".step7.done"
    if sentinel.exists():
        print("[step7] Skip — already done")
        return output_dir / "banner_youtube.jpg"

    resolved_url = ollama_url or os.environ.get("OLLAMA_URL", _DEFAULT_OLLAMA_URL)

    # Locate composed video (prefer youtube, fall back to tiktok)
    video_path = output_dir / "final_youtube.mp4"
    if not video_path.exists():
        video_path = output_dir / "final_tiktok.mp4"
    if not video_path.exists():
        raise FileNotFoundError(
            f"No composed video found in {output_dir}. Run step 6 (compose) first."
        )

    # Load metadata for context
    video_title = ""
    metadata_path = output_dir / "metadata.json"
    if metadata_path.exists():
        video_title = json.loads(metadata_path.read_text()).get("title", "")

    srt_context = ""
    srt_path = output_dir / "captions_vn.srt"
    if srt_path.exists():
        lines = srt_path.read_text(encoding="utf-8").splitlines()
        text_lines = [
            l for l in lines if l and not l.isdigit() and "-->" not in l
        ][:10]
        srt_context = "\n".join(text_lines)

    scenes_path = output_dir / "scenes.json"

    # ── 1. Extract candidate frames ──────────────────────────────────────────
    print("[step7] Extracting candidate frames...")
    frames = extract_candidates(
        video_path,
        scenes_path=scenes_path if scenes_path.exists() else None,
        max_candidates=5,
    )
    if not frames:
        raise RuntimeError("No frames could be extracted from the video.")
    print(f"[step7] {len(frames)} candidates scored")

    # ── 2. LLM frame selection + hook title ──────────────────────────────────
    print(f"[step7] Asking {model} to select best frame + hook title...")
    try:
        frame_idx, title = _call_llm(
            frames,
            srt_context=srt_context,
            video_title=video_title,
            model=model,
            ollama_url=resolved_url,
            api_key=api_key,
        )
        print(f"[step7] Frame {frame_idx} selected — title: {title!r}")
    except Exception as exc:
        print(f"[step7] LLM failed ({exc}) — using top frame and original title")
        frame_idx = 0
        title = (video_title or "Video Hay Nhất").split(" - ")[0][:40]

    chosen_frame = frames[frame_idx]

    # ── 3. Compose and save banners ──────────────────────────────────────────
    platforms = ["youtube", "tiktok"] if platform == "both" else [platform]
    out_path = output_dir / "banner_youtube.jpg"

    for plt in platforms:
        print(f"[step7] Composing {plt} banner ({chosen_frame.shape[1]}×{chosen_frame.shape[0]} → target)...")
        img = compose_banner(chosen_frame, title, plt)
        out_file = output_dir / f"banner_{plt}.jpg"
        img.save(str(out_file), "JPEG", quality=95, optimize=True)
        print(f"[step7] Saved {out_file}")
        if plt == "youtube":
            out_path = out_file

    sentinel.touch()
    return out_path
