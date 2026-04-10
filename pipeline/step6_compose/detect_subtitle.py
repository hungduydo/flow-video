"""
Detect where burned-in subtitle/title text appears in a video using a vision LLM.

Strategy:
  1. Sample n_frames evenly from the middle 60% of the video.
  2. Ask the LLM for the bounding box (x, y, w, h) of any burned-in subtitle
     or title text in each frame (normalised 0-1 coordinates).
  3. Aggregate detections: min(x), avg(y), max(w), avg(h).
  4. Convert to pixels and add 10 px padding on every side.

Returns the padded pixel bounding box (x, y, w, h), or None if nothing found.
Used by compose() to place Vietnamese subtitles outside this region.
"""

import base64
import json
import os
from pathlib import Path

import cv2


_LLM_SYSTEM_PROMPT = """\
You are a video subtitle/title detector. Given a single video frame, identify \
any persistent burned-in subtitle, caption, or title text overlay.

MUST: Respond ONLY with valid JSON matching exactly this schema — no markdown, no prose:
{
  "subtitle": {
    "detected": <true|false>,
    "x":      <float 0-1, left edge normalised to frame width>,
    "y":      <float 0-1, top edge normalised to frame height>,
    "width":  <float 0-1, normalised to frame width>,
    "height": <float 0-1, normalised to frame height>
  }
}

Rules:
- Only report burned-in text overlays: title cards, captions, channel names.
  Do NOT report text that is part of the actual scene content (signs, screens, books).
- If no overlay detected, return {"subtitle": {"detected": false, "x": 0, "y": 0, "width": 0, "height": 0}}
- x, y, width, height must be 0 when detected=false.
- When unsure, return detected=false.
"""


def _frame_to_b64(frame) -> str:
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
    content = (
        response.message.content
        if hasattr(response, "message")
        else response.get("message", {}).get("content", "")
    )
    if not content:
        raise RuntimeError(f"Empty response from model {model!r}: {response}")
    # Strip markdown code fences if the model wraps its response
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def detect_subtitle_region(
    video_path: Path,
    n_frames: int = 5,
    ollama_url: str = "https://ollama.com",
    model: str = "gemini-3-flash-preview:cloud",
    api_key: str | None = None,
    verbose: bool = False,
) -> tuple[int, int, int, int] | None:
    """Detect the bounding box of burned-in subtitle/title text in a video.

    Samples n_frames from the middle 60% of the video, asks the LLM for a
    normalised (x, y, w, h) bounding box per frame, then aggregates:
        final_x = min(x values)
        final_y = avg(y values)
        final_w = max(w values)
        final_h = avg(h values)

    Converts to pixels and pads 10 px on every side.

    Returns:
        (x, y, w, h) in pixels — padded bounding box of the detected region.
        None if the LLM detected no subtitle in the majority of sampled frames.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    try:
        total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        vid_w  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        vid_h  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        start   = int(total * 0.20)
        end     = int(total * 0.80)
        indices = [
            int(start + i * (end - start) / max(n_frames - 1, 1))
            for i in range(n_frames)
        ]

        xs: list[float] = []
        ys: list[float] = []
        ws: list[float] = []
        hs: list[float] = []

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
                    "content": "Detect any burned-in subtitle or title text and return its bounding box.",
                    "images": [b64],
                },
            ]

            try:
                raw  = _ollama_chat(messages, model, ollama_url, api_key=api_key)
                data = json.loads(raw)
                sub  = data.get("subtitle", {})

                if not sub.get("detected", False):
                    if verbose:
                        print(f"[detect_subtitle] frame {frame_idx}: not detected")
                    continue

                x = float(sub["x"])
                y = float(sub["y"])
                w = float(sub["width"])
                h = float(sub["height"])

                xs.append(x)
                ys.append(y)
                ws.append(w)
                hs.append(h)

                if verbose:
                    print(
                        f"[detect_subtitle] frame {frame_idx}: "
                        f"x={x:.3f} y={y:.3f} w={w:.3f} h={h:.3f}"
                    )

            except json.JSONDecodeError as exc:
                if verbose:
                    print(f"[detect_subtitle] frame {frame_idx}: JSON parse error — {exc}")
            except (KeyError, ValueError, TypeError) as exc:
                if verbose:
                    print(f"[detect_subtitle] frame {frame_idx}: invalid data — {exc}")
            except Exception as exc:
                if verbose:
                    print(f"[detect_subtitle] frame {frame_idx}: error — {exc}")

    finally:
        cap.release()

    threshold = max(1, n_frames // 2)
    if len(xs) < threshold:
        if verbose:
            print(
                f"[detect_subtitle] only {len(xs)}/{n_frames} frames detected subtitle "
                f"(threshold={threshold}) — returning None"
            )
        return None

    # Aggregate: widest possible box that covers all detections
    agg_x = min(xs)
    agg_y = sum(ys) / len(ys)
    agg_w = max(ws)
    agg_h = sum(hs) / len(hs)

    if verbose:
        print(
            f"[detect_subtitle] aggregated (normalised): "
            f"x={agg_x:.3f} y={agg_y:.3f} w={agg_w:.3f} h={agg_h:.3f}"
        )

    # Convert to pixels
    pad = 10
    px = max(0,       int(agg_x * vid_w) - pad)
    py = max(0,       int(agg_y * vid_h) - pad)
    pw = min(vid_w - px, int(agg_w * vid_w) + pad * 2)
    ph = min(vid_h - py, int(agg_h * vid_h) + pad * 2)

    if verbose:
        print(f"[detect_subtitle] final box (pixels, +{pad}px pad): x={px} y={py} w={pw} h={ph}")

    return px, py, pw, ph
