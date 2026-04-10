"""
Step: Remove Logo / Watermark

Standalone pipeline step — takes any video and outputs a clean version
with all persistent corner watermarks/logos removed.

Detection:
  Samples ~30 frames and computes per-pixel standard deviation across
  the 4 corner regions. Static watermarks have very low variance compared
  to moving background content. ALL corners above the threshold are returned.

Removal modes:
  fast  — ffmpeg filter chain (real-time): delogo for non-edge regions,
          crop+avgblur+overlay for edge-touching regions. All regions
          removed in a single ffmpeg pass.
  high  — OpenCV TELEA inpainting per-frame with a combined mask covering
          all detected regions.

Usage:
  remove_logo(input_path, output_path, quality='fast')

CLI:
  python -m pipeline.step_remove_logo input.mp4 [output.mp4] [--quality fast|high] [--detect-only]
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


# ── Detection constants ────────────────────────────────────────────────────────

# Corner region proportions for detection (fraction of frame dimensions).
_CORNER_W_RATIO = 0.22
_CORNER_H_RATIO = 0.09

# When the mask hits the inner boundary, expand removal to this ratio.
_EXPAND_W_RATIO = 0.40
_EXPAND_H_RATIO = 0.12

# Minimum removal region size regardless of mask extent (fraction of frame).
# Ensures small logos like semi-transparent icons are fully covered.
_MIN_REMOVAL_W_RATIO = 0.10
_MIN_REMOVAL_H_RATIO = 0.07

# Normal mode — primary: strict temporal variance (pixels always the same).
_VARIANCE_STRICT = 12.0
_MIN_STATIC_PIXELS = 150

# Normal mode — secondary: loose variance + spatial sharpness must both agree.
# Catches semi-transparent / colored logos that the strict threshold misses.
_VARIANCE_LOOSE = 35.0
_SHARPNESS_BLUR_KERNEL = 15   # Gaussian kernel for temporal-mean blurring
_SHARPNESS_THRESHOLD = 8.0    # |mean - blurred| > this = sharp pixel
_MIN_LOOSE_PIXELS = 150       # both loose-variance and sharpness need this many
_SHARPNESS_RATIO_MIN = 1.5    # corner mean_sharp must be > 1.5× lowest corner

# Static-background mode: when all corners appear static, temporal variance
# cannot discriminate — use sharpness normalized by the video center instead.
_STATIC_BG_THRESHOLD = 10000  # if max corner variance<STRICT count exceeds this,
                               # switch to static-background mode
_CENTER_RATIO_MIN = 3.0        # corner mean_sharp / center mean_sharp > this = logo

# Dilation padding around detected mask.
_DILATE_PX = 6


# ── Detection ─────────────────────────────────────────────────────────────────

def _corner_rects(width: int, height: int) -> dict[str, tuple[int, int, int, int]]:
    """Return (x, y, w, h) for each of the 4 corner detection regions."""
    cw = int(width * _CORNER_W_RATIO)
    ch = int(height * _CORNER_H_RATIO)
    return {
        "top_left":     (0,          0,           cw, ch),
        "top_right":    (width - cw, 0,           cw, ch),
        "bottom_left":  (0,          height - ch, cw, ch),
        "bottom_right": (width - cw, height - ch, cw, ch),
    }


def _bbox_for_corner(
    corner: str,
    xs: np.ndarray,
    ys: np.ndarray,
    cx0: int, cy0: int, cw0: int, ch0: int,
    vid_w: int, vid_h: int,
) -> tuple[int, int, int, int]:
    """Compute the final removal bounding box (x, y, w, h) for one corner.

    Anchors to the nearest frame edges (watermarks are always corner-anchored)
    and expands inward if the mask touches the detection zone boundary.
    """
    # Convert crop-relative coordinates to full-frame
    x1 = int(xs.min()) + cx0
    y1 = int(ys.min()) + cy0
    x2 = int(xs.max()) + cx0
    y2 = int(ys.max()) + cy0

    # Anchor to the corner's nearest frame edges
    if corner in ("top_left", "bottom_left"):
        x1 = 0
    else:
        x2 = vid_w - 1

    if corner in ("top_left", "top_right"):
        y1 = 0
    else:
        y2 = vid_h - 1

    # If mask hits the inner detection boundary, expand inward to cover overflow.
    expand_w = int(vid_w * _EXPAND_W_RATIO)
    expand_h = int(vid_h * _EXPAND_H_RATIO)
    if x2 >= cx0 + cw0 - _DILATE_PX - 2:
        x2 = (expand_w - 1) if cx0 == 0 else (vid_w - 1)
    if x1 <= cx0 + _DILATE_PX + 2 and cx0 > 0:
        x1 = vid_w - expand_w
    if y2 >= cy0 + ch0 - _DILATE_PX - 2:
        y2 = (expand_h - 1) if cy0 == 0 else (vid_h - 1)
    if y1 <= cy0 + _DILATE_PX + 2 and cy0 > 0:  # bottom corner, mask at zone top
        y1 = vid_h - expand_h

    # Enforce minimum removal size so small/faint logos are fully covered.
    min_w = int(vid_w * _MIN_REMOVAL_W_RATIO)
    min_h = int(vid_h * _MIN_REMOVAL_H_RATIO)
    if x2 - x1 + 1 < min_w:
        if corner in ("top_left", "bottom_left"):
            x2 = x1 + min_w - 1
        else:
            x1 = x2 - min_w + 1
    if y2 - y1 + 1 < min_h:
        if corner in ("top_left", "top_right"):
            y2 = y1 + min_h - 1
        else:
            y1 = y2 - min_h + 1

    # Clamp
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(vid_w - 1, x2)
    y2 = min(vid_h - 1, y2)

    return x1, y1, x2 - x1 + 1, y2 - y1 + 1


def detect_watermark_regions(
    video_path: Path,
    n_frames: int = 30,
    verbose: bool = False,
) -> list[tuple[str, int, int, int, int]]:
    """Detect ALL corners that contain a static watermark/logo.

    Uses two detection modes:
    - Normal mode (dynamic background): temporal variance (strict + loose+sharpness combo)
    - Static-background mode (e.g. curtain/wall): sharpness ratio vs video center

    Returns a list of (corner_name, x, y, w, h). Empty list = no watermark.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if total_frames < 2:
        cap.release()
        return []

    rects = _corner_rects(vid_w, vid_h)
    cw0 = int(vid_w * _CORNER_W_RATIO)
    ch0 = int(vid_h * _CORNER_H_RATIO)
    center_rect = ((vid_w - cw0) // 2, (vid_h - ch0) // 2, cw0, ch0)

    sample_count = min(n_frames, total_frames)
    indices = [int(i * total_frames / sample_count) for i in range(sample_count)]

    corner_crops: dict[str, list[np.ndarray]] = {c: [] for c in rects}
    center_crops: list[np.ndarray] = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for corner, (cx, cy, cw, ch) in rects.items():
            corner_crops[corner].append(gray[cy:cy+ch, cx:cx+cw])
        cx2, cy2, cw2, ch2 = center_rect
        center_crops.append(gray[cy2:cy2+ch2, cx2:cx2+cw2])

    cap.release()

    # ── Compute per-corner statistics ──────────────────────────────────────────

    def _sharpness_mean(crops: list[np.ndarray]) -> float:
        mean_img = np.mean(np.stack(crops, axis=0), axis=0).astype(np.float32)
        blurred = cv2.GaussianBlur(
            mean_img, (_SHARPNESS_BLUR_KERNEL, _SHARPNESS_BLUR_KERNEL), 0
        )
        return float(np.abs(mean_img - blurred).mean())

    center_sharp = _sharpness_mean(center_crops) if center_crops else 1.0

    corner_stats: dict[str, dict] = {}
    for corner, crops in corner_crops.items():
        if len(crops) < 5:
            continue
        stack = np.stack(crops, axis=0)
        std_map = np.std(stack, axis=0)

        mean_img = np.mean(stack, axis=0).astype(np.float32)
        blurred = cv2.GaussianBlur(
            mean_img, (_SHARPNESS_BLUR_KERNEL, _SHARPNESS_BLUR_KERNEL), 0
        )
        sharp_map = np.abs(mean_img - blurred)

        corner_stats[corner] = {
            "std_map": std_map,
            "sharp_map": sharp_map,
            "count_strict": int(np.count_nonzero(std_map < _VARIANCE_STRICT)),
            "count_loose":  int(np.count_nonzero(std_map < _VARIANCE_LOOSE)),
            "count_sharp":  int(np.count_nonzero(sharp_map > _SHARPNESS_THRESHOLD)),
            "mean_sharp":   float(sharp_map.mean()),
        }

    if not corner_stats:
        return []

    # ── Decide detection mode ──────────────────────────────────────────────────

    max_strict = max(s["count_strict"] for s in corner_stats.values())
    static_bg_mode = max_strict > _STATIC_BG_THRESHOLD

    min_mean_sharp = min(s["mean_sharp"] for s in corner_stats.values())

    if verbose:
        mode_label = "static-background" if static_bg_mode else "normal"
        print(f"[remove_logo/detect] mode={mode_label}  max_strict={max_strict}  "
              f"center_sharp={center_sharp:.3f}  min_mean_sharp={min_mean_sharp:.3f}")
        print(f"[remove_logo/detect] thresholds: strict={_VARIANCE_STRICT} loose={_VARIANCE_LOOSE} "
              f"sharpness_th={_SHARPNESS_THRESHOLD} sharpness_ratio_min={_SHARPNESS_RATIO_MIN} "
              f"center_ratio_min={_CENTER_RATIO_MIN}")

    # ── Evaluate each corner ───────────────────────────────────────────────────

    kernel = np.ones((_DILATE_PX, _DILATE_PX), np.uint8)
    results: list[tuple[str, int, int, int, int]] = []

    for corner, s in corner_stats.items():
        if static_bg_mode:
            # Background is static — only trust sharpness normalized by center
            center_ratio = s["mean_sharp"] / max(center_sharp, 0.001)
            detected = center_ratio > _CENTER_RATIO_MIN
            logo_mask = (s["sharp_map"] > _SHARPNESS_THRESHOLD).astype(np.uint8) * 255
            if verbose:
                mark = "DETECTED" if detected else "skip"
                print(f"[remove_logo/detect]   {corner:14s}  mean_sharp={s['mean_sharp']:.3f}  "
                      f"center_ratio={center_ratio:.2f}  [{mark}]")
        else:
            # Normal mode
            # Primary: strict temporal variance alone
            primary = s["count_strict"] >= _MIN_STATIC_PIXELS
            # Secondary: loose variance AND sharpness both pass, with relative boost
            secondary = (
                s["count_loose"] >= _MIN_LOOSE_PIXELS
                and s["count_sharp"] >= _MIN_LOOSE_PIXELS
                and s["mean_sharp"] >= min_mean_sharp * _SHARPNESS_RATIO_MIN
            )
            detected = primary or secondary
            logo_mask = cv2.bitwise_or(
                (s["std_map"] < _VARIANCE_STRICT).astype(np.uint8) * 255,
                (s["sharp_map"] > _SHARPNESS_THRESHOLD).astype(np.uint8) * 255,
            )
            if verbose:
                sharp_ratio = s["mean_sharp"] / max(min_mean_sharp, 0.001)
                mark = "DETECTED" if detected else "skip"
                reason = ("primary" if primary else "secondary" if secondary else "—")
                print(f"[remove_logo/detect]   {corner:14s}  "
                      f"strict={s['count_strict']:5d}(>={_MIN_STATIC_PIXELS})  "
                      f"loose={s['count_loose']:5d}  "
                      f"sharp_px={s['count_sharp']:5d}  "
                      f"mean_sharp={s['mean_sharp']:.3f}  "
                      f"sharp_ratio={sharp_ratio:.2f}  "
                      f"[{mark} / {reason}]")

        if not detected:
            continue

        dilated = cv2.dilate(logo_mask, kernel, iterations=1)
        ys, xs = np.where(dilated > 0)
        if len(xs) == 0:
            continue

        cx0, cy0, cw0, ch0 = rects[corner]
        x, y, w, h = _bbox_for_corner(corner, xs, ys, cx0, cy0, cw0, ch0, vid_w, vid_h)
        results.append((corner, x, y, w, h))

    return results


# Keep single-result API for backward compatibility
def detect_watermark_region(
    video_path: Path,
    n_frames: int = 30,
) -> tuple[str, int, int, int, int] | None:
    """Detect the first (strongest) watermark corner. Returns None if not found."""
    regions = detect_watermark_regions(video_path, n_frames)
    return regions[0] if regions else None


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
) -> tuple[str, str, list[str]]:
    """Build ffmpeg -vf filter string to remove all regions in one pass.

    Uses delogo for all regions (including edge-touching corners). delogo
    interpolates from the border pixels of the rectangle and handles frame
    edges correctly in modern ffmpeg — no need for a separate blur path.

    Returns (filter_flag, filter_string, extra_map_args).
    """
    pad = 10
    filters = []
    for (_, x, y, w, h) in regions:
        x1 = max(3, x - pad)
        y1 = max(3, y - pad)
        x2 = min(vid_w - 3, x + w + pad)
        y2 = min(vid_h - 3, y + h + pad)
        filters.append(f"delogo=x={x1}:y={y1}:w={x2 - x1}:h={y2 - y1}")
    return "-vf", ",".join(filters), []


# ── Removal ────────────────────────────────────────────────────────────────────

def _remove_fast(
    input_path: Path,
    output_path: Path,
    regions: list[tuple[str, int, int, int, int]],
) -> None:
    """Remove all logo regions with ffmpeg delogo in a single pass."""
    vid_w, vid_h = _get_dimensions(input_path)
    _, filter_str, _ = _build_removal_filter(regions, vid_w, vid_h)

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


def _remove_high(
    input_path: Path,
    output_path: Path,
    regions: list[tuple[str, int, int, int, int]],
) -> None:
    """Remove all logo regions with OpenCV TELEA inpainting (higher quality)."""
    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Combined mask covering all regions
    mask = np.zeros((vid_h, vid_w), dtype=np.uint8)
    for (_, x, y, w, h) in regions:
        mask[y:y+h, x:x+w] = 255

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    writer_cmd = [
        _ffmpeg_bin(), "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{vid_w}x{vid_h}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-movflags", "+faststart", str(tmp_path),
    ]
    proc = subprocess.Popen(writer_cmd, stdin=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        inpainted = cv2.inpaint(frame, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        proc.stdin.write(inpainted.tobytes())
        frame_idx += 1
        if frame_idx % 100 == 0:
            pct = frame_idx / max(total, 1) * 100
            print(f"\r[remove_logo] inpainting {frame_idx}/{total} ({pct:.0f}%)",
                  end="", flush=True)

    cap.release()
    proc.stdin.close()
    proc.wait()
    print()

    if proc.returncode != 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError("OpenCV inpainting ffmpeg writer failed")

    mux_cmd = [
        _ffmpeg_bin(), "-y",
        "-i", str(tmp_path), "-i", str(input_path),
        "-map", "0:v:0", "-map", "1:a:0?",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart", str(output_path),
    ]
    result = subprocess.run(mux_cmd, capture_output=True, text=True)
    tmp_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed:\n{result.stderr[-3000:]}")


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
    """Encode an OpenCV BGR frame as a base64 JPEG string."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _make_ollama_client(base_url: str, api_key: str | None) -> "Client":
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
    """Send a chat request via ollama.Client and return the assistant message content."""
    client = _make_ollama_client(base_url, api_key)
    response = client.chat(model=model, messages=messages, stream=False)
    # ollama SDK returns a Pydantic ChatResponse — use attribute access
    content = response.message.content if hasattr(response, 'message') else response.get('message', {}).get('content', '')
    if not content:
        raise RuntimeError(f"Empty response from model {model!r}: {response}")
    
    # Strip markdown code block wrapper if present
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]  # Remove ```json
    elif content.startswith("```"):
        content = content[3:]  # Remove ```
    if content.endswith("```"):
        content = content[:-3]  # Remove trailing ```
    content = content.strip()
    
    return content


def detect_all_regions_llm(
    video_path: Path,
    n_frames: int = 5,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    min_votes: int | None = None,
    verbose: bool = False,
) -> tuple[list[tuple[str, int, int, int, int]], tuple[int, int, int, int] | None]:
    """Detect logo watermarks AND burned-in subtitle region in one LLM pass.

    Samples n_frames from the middle 60% of the video. Each frame is sent to
    the vision LLM once; the response contains both watermark corners and the
    subtitle bounding box.

    Logo aggregation  : majority-vote per corner; average normalised coords.
    Subtitle aggregation: min(x), avg(y), max(w), avg(h) across detected frames,
                          then converted to pixels with 10 px padding.

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
            if not raw or not raw.strip():
                if verbose:
                    print(f"[remove_logo/llm] frame {frame_idx}: empty response")
                continue
            print("hello")
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

        # ── logos ──
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

        # ── subtitle ──
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
    threshold = min_votes if min_votes is not None else max(1, n_frames // 2)
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


def detect_watermark_regions_llm(
    video_path: Path,
    n_frames: int = 5,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    min_votes: int | None = None,
    verbose: bool = False,
) -> list[tuple[str, int, int, int, int]]:
    """Detect watermark/logo regions via Ollama vision LLM.

    Delegates to detect_all_regions_llm() and returns only the logo list.
    Kept for backward compatibility.
    """
    logos, _ = detect_all_regions_llm(
        video_path, n_frames=n_frames, ollama_url=ollama_url, model=model,
        api_key=api_key, min_votes=min_votes, verbose=verbose,
    )
    return logos


# ── Public API ─────────────────────────────────────────────────────────────────

def remove_logo(
    input_path: Path | str,
    output_path: Path | str | None = None,
    quality: str = "fast",
    provider: str = "cv",
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    verbose: bool = False,
) -> Path:
    """Detect and remove all corner watermarks/logos from a video.

    Args:
        input_path:  Path to input video.
        output_path: Path to output video. Defaults to {stem}_clean.mp4.
        quality:     'fast' (ffmpeg) or 'high' (OpenCV inpainting).
        provider:    'cv' (default, pixel-variance) or 'llm' (Ollama Cloud vision).
        ollama_url:  Ollama base URL (default: https://ollama.com for cloud).
        model:       Ollama model name (default: gemma4).
        api_key:     Ollama Cloud API key. Falls back to OLLAMA_API_KEY env var.
        verbose:     Print detection debug info.

    Returns:
        Path to the output video.
    """
    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_clean{input_path.suffix}"
    output_path = Path(output_path)

    if quality not in ("fast", "high"):
        raise ValueError(f"quality must be 'fast' or 'high', got {quality!r}")
    if provider not in ("cv", "llm"):
        raise ValueError(f"provider must be 'cv' or 'llm', got {provider!r}")

    print(f"[remove_logo] Detecting watermarks in {input_path.name} "
          f"(provider={provider!r}) …")

    subtitle_bbox: tuple[int, int, int, int] | None = None
    print("hello")
    if provider == "llm":
        regions, subtitle_bbox = detect_all_regions_llm(
            input_path, ollama_url=ollama_url, model=model,
            api_key=api_key, verbose=verbose,
        )
    else:
        regions = detect_watermark_regions(input_path, verbose=verbose)

    # Save detected regions so downstream steps (e.g. step6_compose) can use them
    _save_detected_regions(input_path.parent, regions, subtitle_bbox)

    if not regions:
        print("[remove_logo] No watermarks detected — copying input unchanged")
        shutil.copy2(input_path, output_path)
        return output_path

    for corner, x, y, w, h in regions:
        print(f"[remove_logo]   {corner}: x={x} y={y} w={w} h={h}")
    print(f"[remove_logo] Removing {len(regions)} region(s) with mode={quality!r} …")

    if quality == "fast":
        _remove_fast(input_path, output_path, regions)
    else:
        _remove_high(input_path, output_path, regions)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"[remove_logo] Done → {output_path} ({size_mb:.1f} MB)")
    return output_path


def _save_detected_regions(
    output_dir: Path,
    logos: list[tuple[str, int, int, int, int]],
    subtitle: tuple[int, int, int, int] | None,
) -> None:
    """Persist detected logo and subtitle regions to detected_regions.json.

    Format:
        {
          "logos": [{"corner": "top_right", "x": 10, "y": 5, "w": 100, "h": 50}],
          "subtitle": {"x": 50, "y": 950, "w": 1820, "h": 80}  // or null
        }

    step6_compose reads this file to decide where to place Vietnamese subtitles
    and whether to delogo the original subtitle region.
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
