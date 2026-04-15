"""
Step: Remove Logo / Watermark

Detects persistent corner watermarks/logos and burned-in subtitles using an
Ollama vision LLM, then removes them with ffmpeg delogo in a single pass.

Usage:
  remove_logo(input_path, output_path)

CLI:
  python -m pipeline.step_remove_logo input.mp4 [output.mp4] [--detect-only]
"""

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import cv2
import numpy as np


# ── LLM detection (Ollama vision) ─────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are a video overlay detector. Given a single video frame, identify:
1. Every persistent channel logo, network bug, or watermark in any corner.
2. Any burned-in subtitle, caption, or title text overlay anywhere in the frame.

MUST: Respond ONLY with valid JSON matching exactly this schema — no markdown, no prose:
{
  "watermarks": [
    {
      "corner": "<top_left|top_right|bottom_left|bottom_right>",
      "x": <float 0-1, left edge normalised to frame width>,
      "y": <float 0-1, top edge normalised to frame height>,
      "width": <float 0-1, normalised>,
      "height": <float 0-1, normalised>
    }
  ],
  "subtitle": {
    "detected": <true|false>,
    "x":      <float 0-1, left edge normalised to frame width>,
    "y":      <float 0-1, top edge normalised to frame height>,
    "width":  <float 0-1, normalised>,
    "height": <float 0-1, normalised>
  }
}

Rules:
- watermarks: only persistent corner overlays (logos, bugs, channel IDs, copyright). Empty array if none.
- subtitle: burned-in text overlays (title cards, captions, channel names). NOT scene text (signs, books, screens in the video).
- subtitle x/y/width/height must be 0 when detected=false.
- Be conservative: when unsure, omit watermarks and set subtitle detected=false.
"""


def _frame_to_b64(frame: np.ndarray) -> str:
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _make_ollama_client(base_url: str, api_key: str | None):
    from ollama import Client
    resolved_key = api_key or os.environ.get("OLLAMA_API_KEY", "")
    return Client(
        host=base_url,
        headers={"Authorization": f"Bearer {resolved_key}"} if resolved_key else {},
    )


def _ollama_chat(
    messages: list[dict],
    model: str,
    base_url: str,
    api_key: str | None = None,
) -> str:
    client = _make_ollama_client(base_url, api_key)
    response = client.chat(model=model, messages=messages, stream=False)
    content = response.message.content if hasattr(response, "message") else response.get("message", {}).get("content", "")
    if not content:
        raise RuntimeError(f"Empty response from model {model!r}: {response}")
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def detect_all_regions_llm(
    video_path: Path,
    n_frames: int = 5,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    min_votes: int | None = None,
    verbose: bool = False,
) -> tuple[list[tuple[str, int, int, int, int]], tuple[int, int, int, int] | None]:
    """Detect logo watermarks AND burned-in subtitle region via Ollama vision LLM.

    Samples n_frames from the middle 60% of the video. Each frame is sent once;
    the response contains both watermark corners and the subtitle bounding box.

    Logo aggregation  : majority-vote per corner; average normalised coords.
    Subtitle aggregation: min(x), avg(y), max(w), avg(h) + 10 px padding.

    Returns:
        (logos, subtitle_bbox)
        logos        — list of (corner_name, x, y, w, h) in pixels
        subtitle_bbox — (x, y, w, h) in pixels with 10 px pad, or None
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    start = int(total * 0.20)
    end   = int(total * 0.80)
    indices = [
        int(start + i * (end - start) / max(n_frames - 1, 1))
        for i in range(n_frames)
    ]

    valid_corners = {"top_left", "top_right", "bottom_left", "bottom_right"}
    logo_votes: dict[str, list[tuple[float, float, float, float]]] = {}
    sub_xs: list[float] = []
    sub_ys: list[float] = []
    sub_ws: list[float] = []
    sub_hs: list[float] = []

    for frame_idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            continue

        b64 = _frame_to_b64(frame)
        messages = [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Detect all watermarks/logos and any burned-in subtitle or title text in this video frame.",
                "images": [b64],
            },
        ]

        try:
            raw = _ollama_chat(messages, model, ollama_url, api_key=api_key)
            if not raw:
                if verbose:
                    print(f"[remove_logo/llm] frame {frame_idx}: empty response")
                continue
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            if verbose:
                print(f"[remove_logo/llm] frame {frame_idx}: JSON parse error — {exc}")
                print(f"[remove_logo/llm]   raw: {repr(raw[:200])}")
            continue
        except Exception as exc:
            if verbose:
                print(f"[remove_logo/llm] frame {frame_idx}: error — {exc}")
            continue

        for wm in data.get("watermarks", []):
            corner = wm.get("corner", "")
            if corner not in valid_corners:
                continue
            try:
                entry = (float(wm["x"]), float(wm["y"]),
                         float(wm["width"]), float(wm["height"]))
            except (KeyError, ValueError, TypeError):
                continue
            logo_votes.setdefault(corner, []).append(entry)

        sub = data.get("subtitle", {})
        if sub.get("detected", False):
            try:
                sub_xs.append(float(sub["x"]))
                sub_ys.append(float(sub["y"]))
                sub_ws.append(float(sub["width"]))
                sub_hs.append(float(sub["height"]))
                if verbose:
                    print(f"[remove_logo/llm] frame {frame_idx}: subtitle "
                          f"x={sub['x']:.3f} y={sub['y']:.3f} "
                          f"w={sub['width']:.3f} h={sub['height']:.3f}")
            except (KeyError, ValueError, TypeError):
                pass
        elif verbose:
            print(f"[remove_logo/llm] frame {frame_idx}: no subtitle detected")

    cap.release()

    # ── aggregate logos ──
    threshold = min_votes if min_votes is not None else max(1, n_frames // 3)
    logo_results: list[tuple[str, int, int, int, int]] = []
    for corner, detections in logo_votes.items():
        n = len(detections)
        if verbose:
            print(f"[remove_logo/llm] logo {corner}: {n}/{n_frames} votes (need {threshold})")
        if n < threshold:
            continue
        avg_x = sum(d[0] for d in detections) / n
        avg_y = sum(d[1] for d in detections) / n
        avg_w = sum(d[2] for d in detections) / n
        avg_h = sum(d[3] for d in detections) / n
        px = max(0, int(avg_x * vid_w))
        py = max(0, int(avg_y * vid_h))
        pw = min(int(avg_w * vid_w), vid_w - px)
        ph = min(int(avg_h * vid_h), vid_h - py)
        if verbose:
            print(f"[remove_logo/llm]   logo → x={px} y={py} w={pw} h={ph}")
        logo_results.append((corner, px, py, pw, ph))

    # ── aggregate subtitle: min(x), avg(y), max(w), avg(h) + 10 px pad ──
    subtitle_bbox: tuple[int, int, int, int] | None = None
    if len(sub_xs) >= threshold:
        pad = 10
        agg_x = min(sub_xs)
        agg_y = sum(sub_ys) / len(sub_ys)
        agg_w = max(sub_ws)
        agg_h = sum(sub_hs) / len(sub_hs)
        sx = max(0,       int(agg_x * vid_w) - pad)
        sy = max(0,       int(agg_y * vid_h) - pad)
        sw = min(vid_w - sx, int(agg_w * vid_w) + pad * 2)
        sh = min(vid_h - sy, int(agg_h * vid_h) + pad * 2)
        subtitle_bbox = (sx, sy, sw, sh)
        if verbose:
            print(f"[remove_logo/llm] subtitle → x={sx} y={sy} w={sw} h={sh} "
                  f"(from {len(sub_xs)}/{n_frames} frames, +{pad}px pad)")
    elif verbose:
        print(f"[remove_logo/llm] subtitle: only {len(sub_xs)}/{n_frames} detections "
              f"(need {threshold}) — not reported")

    return logo_results, subtitle_bbox


# ── ffmpeg helpers ─────────────────────────────────────────────────────────────

def _ffmpeg_bin() -> str:
    full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
    return str(full) if full.exists() else "ffmpeg"


def _get_dimensions(video_path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return 1920, 1080
    parts = result.stdout.strip().split(",")
    return int(parts[0]), int(parts[1])


def _build_removal_filter(
    regions: list[tuple[str, int, int, int, int]],
    vid_w: int,
    vid_h: int,
) -> str:
    """Build ffmpeg -vf filter string to remove all regions in one pass."""
    pad = 10
    filters = []
    for (_, x, y, w, h) in regions:
        x1 = max(3, x - pad)
        y1 = max(3, y - pad)
        x2 = min(vid_w - 3, x + w + pad)
        y2 = min(vid_h - 3, y + h + pad)
        filters.append(f"delogo=x={x1}:y={y1}:w={x2 - x1}:h={y2 - y1}")
    return ",".join(filters)


def _remove_regions(
    input_path: Path,
    output_path: Path,
    regions: list[tuple[str, int, int, int, int]],
) -> None:
    """Remove all regions with ffmpeg delogo in a single pass."""
    vid_w, vid_h = _get_dimensions(input_path)
    filter_str = _build_removal_filter(regions, vid_w, vid_h)

    cmd = [
        _ffmpeg_bin(), "-y", "-i", str(input_path),
        "-vf", filter_str,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "copy", "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg logo removal failed:\n{result.stderr[-3000:]}")


# ── Persistence ────────────────────────────────────────────────────────────────

def _save_detected_regions(
    output_dir: Path,
    logos: list[tuple[str, int, int, int, int]],
    subtitle: tuple[int, int, int, int] | None,
) -> None:
    """Persist detected logo and subtitle regions to detected_regions.json.

    step6_compose reads this file to place Vietnamese subtitles and optionally
    delogo the original subtitle region.

    Format:
        {
          "logos": [{"corner": "top_right", "x": 10, "y": 5, "w": 100, "h": 50}],
          "subtitle": {"x": 50, "y": 950, "w": 1820, "h": 80}  // or null
        }
    """
    data: dict = {
        "logos": [
            {"corner": corner, "x": x, "y": y, "w": w, "h": h}
            for corner, x, y, w, h in logos
        ],
        "subtitle": (
            {"x": subtitle[0], "y": subtitle[1], "w": subtitle[2], "h": subtitle[3]}
            if subtitle else None
        ),
    }
    path = output_dir / "detected_regions.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[remove_logo] Saved detected regions → {path}")


# ── Public API ─────────────────────────────────────────────────────────────────

def remove_logo(
    input_path: Path | str,
    output_path: Path | str | None = None,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    verbose: bool = False,
) -> Path:
    """Detect and remove all corner watermarks/logos from a video via LLM.

    Args:
        input_path:  Path to input video.
        output_path: Path to output video. Defaults to {stem}_clean.mp4.
        ollama_url:  Ollama base URL (default: https://ollama.com for cloud).
        model:       Ollama model name.
        api_key:     Ollama Cloud API key. Falls back to OLLAMA_API_KEY env var.
        verbose:     Print per-frame LLM detection results.

    Returns:
        Path to the output video.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_clean{input_path.suffix}"
    output_path = Path(output_path)

    print(f"[remove_logo] Detecting watermarks in {input_path.name} (model={model!r}) …")

    regions, subtitle_bbox = detect_all_regions_llm(
        input_path, ollama_url=ollama_url, model=model,
        api_key=api_key, verbose=verbose,
    )

    # Enforce minimum subtitle bbox width of 60% of frame width
    if subtitle_bbox:
        vid_w, _ = _get_dimensions(input_path)
        min_w = int(vid_w * 0.60)
        sx, sy, sw, sh = subtitle_bbox
        if sw < min_w:
            new_sx = max(0, (vid_w - min_w) // 2)
            subtitle_bbox = (new_sx, sy, min_w, sh)
            print(f"[remove_logo] Subtitle bbox width {sw}px → expanded to {min_w}px (60% of {vid_w}px)")

    _save_detected_regions(input_path.parent, regions, subtitle_bbox)

    all_regions = list(regions)
    if subtitle_bbox:
        all_regions.append(("subtitle", *subtitle_bbox))

    if not all_regions:
        print("[remove_logo] No watermarks or subtitle detected — copying input unchanged")
        shutil.copy2(input_path, output_path)
        return output_path

    for corner, x, y, w, h in regions:
        print(f"[remove_logo]   {corner}: x={x} y={y} w={w} h={h}")
    if subtitle_bbox:
        sx, sy, sw, sh = subtitle_bbox
        print(f"[remove_logo]   subtitle: x={sx} y={sy} w={sw} h={sh}")
    print(f"[remove_logo] Removing {len(all_regions)} region(s) …")

    _remove_regions(input_path, output_path, all_regions)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"[remove_logo] Done → {output_path} ({size_mb:.1f} MB)")
    return output_path


def clean(
    output_dir: Path,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    verbose: bool = False,
) -> Path:
    """Step 1c: detect + remove logos + subtitle from original.mp4 → original_clean.mp4.

    Writes detected_regions.json for use by step6_compose.
    Sentinel: .step1c.done
    """
    output_dir = Path(output_dir)
    sentinel   = output_dir / ".step1c.done"
    clean_path = output_dir / "original_clean.mp4"

    if sentinel.exists():
        print("[step1c] Skip — already done")
        return clean_path if clean_path.exists() else output_dir / "original.mp4"

    input_path = output_dir / "original.mp4"
    if not input_path.exists():
        raise FileNotFoundError(f"Required file missing: {input_path}")

    result = remove_logo(
        input_path,
        output_path=clean_path,
        ollama_url=ollama_url,
        model=model,
        api_key=api_key,
        verbose=verbose,
    )

    sentinel.touch()
    print(f"[step1c] Done → {result}")
    return result
