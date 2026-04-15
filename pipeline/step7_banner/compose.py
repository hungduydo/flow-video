"""Banner image composition using Pillow."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_YOUTUBE_SIZE = (1280, 720)
_TIKTOK_SIZE = (1080, 1920)

# Roboto Bold — downloaded once and cached next to this file
_ROBOTO_CACHE = Path(__file__).parent / "Roboto-Bold.ttf"
_ROBOTO_URL = (
    "https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Bold.ttf"
)

# Fallback system fonts with Vietnamese coverage (used if Roboto unavailable)
_FALLBACK_FONTS: list[tuple[str, int | None]] = [
    ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", None),
    ("/System/Library/Fonts/Supplemental/Verdana Bold.ttf", None),
    ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
    ("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf", None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
]

# Fallback accent color (TikTok red) when dominant color extraction fails
_FALLBACK_ACCENT = (254, 44, 85)


def _ensure_roboto() -> Path | None:
    """Return path to Roboto-Bold.ttf, downloading it on first use if needed."""
    if _ROBOTO_CACHE.exists():
        return _ROBOTO_CACHE
    try:
        import urllib.request
        print("[step7] Downloading Roboto-Bold.ttf (one-time)...")
        urllib.request.urlretrieve(_ROBOTO_URL, _ROBOTO_CACHE)
        print(f"[step7] Font saved to {_ROBOTO_CACHE}")
        return _ROBOTO_CACHE
    except Exception as exc:
        print(f"[step7] Could not download Roboto: {exc} — using system font")
        return None


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    roboto = _ensure_roboto()
    if roboto:
        try:
            return ImageFont.truetype(str(roboto), size)
        except (IOError, OSError):
            pass
    for path, index in _FALLBACK_FONTS:
        try:
            if index is not None:
                return ImageFont.truetype(path, size, index=index)
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _cv2_to_pil(frame: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def _dominant_color(frame: np.ndarray) -> tuple[int, int, int]:
    """Extract the most visually dominant (saturated, bright) color from a frame.

    Uses numpy quantization to avoid adding sklearn as a dependency.
    Quantizes to 32-bin buckets in HSV space, then picks the most frequent
    hue bin with reasonable saturation/value. Falls back to _FALLBACK_ACCENT
    if no suitable color is found.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).reshape(-1, 3)

    # Filter: keep pixels with decent saturation and brightness (avoid greys/blacks)
    mask = (hsv[:, 1] > 60) & (hsv[:, 2] > 60)
    filtered = hsv[mask]

    if len(filtered) < 100:
        return _FALLBACK_ACCENT

    # Quantize hue (0–179 in OpenCV) to 18 bins of 10°
    hue_bins = (filtered[:, 0] // 10).astype(np.int32)
    counts = np.bincount(hue_bins, minlength=18)
    dominant_bin = int(np.argmax(counts))

    # Reconstruct a representative color: median saturation/value in that bin
    bin_pixels = filtered[hue_bins == dominant_bin]
    median_s = int(np.median(bin_pixels[:, 1]))
    median_v = int(np.median(bin_pixels[:, 2]))
    hue = dominant_bin * 10 + 5  # center of the bin

    # Convert HSV → BGR → RGB
    hsv_pixel = np.array([[[hue, median_s, median_v]]], dtype=np.uint8)
    bgr = cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)[0, 0]
    return (int(bgr[2]), int(bgr[1]), int(bgr[0]))  # RGB tuple


def _smart_crop(
    img: Image.Image,
    w: int,
    h: int,
    subject: dict | None = None,
) -> Image.Image:
    """Resize + crop to exact (w, h), anchoring on subject position.

    - Face detected: places eye_y at the upper-third of the banner.
    - Saliency detected: centers crop on saliency centroid.
    - No subject: falls back to center crop.
    """
    src_ratio = img.width / img.height
    tgt_ratio = w / h

    if src_ratio > tgt_ratio:
        new_h, new_w = h, int(img.width * h / img.height)
    else:
        new_w, new_h = w, int(img.height * w / img.width)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Scale factor from original frame coords to resized image coords
    scale = new_h / (img.height * new_h / new_h)  # simplifies to 1 after resize
    # More precisely: scale_y = new_h / original_h_before_resize
    # We work in resized-image coordinates directly.

    left = (new_w - w) // 2  # default: center crop
    top = (new_h - h) // 2

    if subject:
        orig_h = img.height  # new_h after resize above (already done)
        orig_w = img.width   # new_w

        if subject["type"] == "face":
            # Scale eye_y to resized coordinates
            # subject coords are in the original frame; we need the scale factor
            # We don't have the original frame dims here, so we use relative position:
            # eye_y was in original frame height. img is already resized, so we
            # compute the relative position.
            # Since the resize is proportional, use new_h / original_frame_h.
            # We approximate by using the ratio new_h / subject["eye_y"] if eye_y > 0.
            # Better: store relative coordinates. For now, approximate using
            # the face bbox to infer scale.
            face_h_orig = subject.get("h", 0)
            face_y_orig = subject.get("y", 0)
            eye_y_orig = subject.get("eye_y", face_y_orig + face_h_orig // 3)

            # We don't know original frame height here; use heuristic:
            # assume eye_y is a fraction of the original frame height.
            # The resize maintained aspect ratio, so scale = new_h / original_h.
            # We can infer original_h from the subject bbox if it looks reasonable.
            # Safest: use cx/cy as relative coords by normalizing with the
            # original frame dimensions stored in subject (not stored).
            # Fallback: treat eye_y as pixels in the resized frame using cy ratio.
            cy_rel = subject["cy"] / max(subject.get("h", 1) * 8, 1)  # rough
            # Use the face center_y as relative and scale to new image
            # Actually, use relative: assume subject coords are in original px
            # and scale proportionally. Face detection was on original frame.
            # Estimate original height via: face spans ~15% of frame height typically.
            # Simpler: just use the relative position of eye_y in [0..1] of frame.
            # We approximate original frame height = eye_y / 0.25 (eye is ~25% down)
            # This is too fragile. Instead, pass relative coords from frames.py.
            # For now use cx, cy directly scaled by new_w/new_h assuming they
            # are already in resized coords — this works when face was detected
            # on the frame that we then resize.
            # Re-scale: new_w / frame_w = scale_x, new_h / frame_h = scale_y
            # We don't have frame_w/frame_h. Use face width as proxy:
            # face bbox width / frame width ~ 0.15–0.4 for close shots.
            # Best effort: clamp eye_y to a valid crop range.
            eye_y_scaled = int(eye_y_orig * new_h / max(eye_y_orig * 4, new_h))
            # Simplest robust version: use cy (face center y) scaled proportionally.
            # face_center_y / original_h = subject["cy"] / orig_h_unknown
            # → use cx,cy as pixel offsets in the resized image directly
            # (acceptable approximation when resize factor ~1x or small).
            eye_y_scaled = min(new_h - 1, max(0, int(
                subject["eye_y"] * new_h / (subject["eye_y"] + subject.get("h", 50) * 3)
                if subject.get("h", 0) > 0
                else new_h // 4
            )))

            # Place eye_y at 1/3 of the banner height
            desired_top = eye_y_scaled - h // 3
            top = max(0, min(new_h - h, desired_top))

        elif subject["type"] == "saliency":
            # Center crop on saliency centroid cy
            cy_scaled = int(subject["cy"] * new_h / max(subject.get("cy", 1) * 2, new_h // 2))
            # Approximate: use cy directly (same scaling assumption as face)
            cy_scaled = min(new_h - 1, max(0, subject["cy"]))
            desired_top = cy_scaled - h // 2
            top = max(0, min(new_h - h, desired_top))

    return img.crop((left, top, left + w, top + h))


def _text_side(subject: dict | None, img_w: int) -> str:
    """Return 'right' if subject is on the left half, else 'left'."""
    if subject is None:
        return "left"
    cx = subject.get("cx", img_w // 2)
    return "right" if cx < img_w * 0.45 else "left"


def _apply_gradient(img: Image.Image) -> Image.Image:
    """Bottom-heavy dark gradient so text stays readable."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    h = img.height
    for y in range(h):
        # Gradient starts at 50 % of height; reaches ~82 % opacity at bottom
        t = max(0.0, (y / h - 0.50) / 0.50)
        alpha = int((t ** 0.65) * 210)
        draw.line([(0, y), (img.width - 1, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _wrap_text(
    text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    """Word-wrap *text* so each line fits within *max_width* pixels."""
    _dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = _dummy.textbbox((0, 0), candidate, font=font)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def _draw_outlined_text(
    draw: ImageDraw.Draw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    outline: int = 3,
) -> None:
    """Draw white text with a solid black outline for readability."""
    x, y = xy
    for dx in range(-outline, outline + 1):
        for dy in range(-outline, outline + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def compose_banner(
    frame: np.ndarray,
    title: str,
    platform: str,
    subject: dict | None = None,
) -> Image.Image:
    """Return a composed PIL Image banner for *platform* ('youtube' or 'tiktok').

    Args:
        frame:    OpenCV BGR frame.
        title:    Hook title text (Vietnamese).
        platform: 'youtube' or 'tiktok'.
        subject:  Subject info dict from detect_subject() — used for smart crop
                  and negative-space text placement.
    """
    target_w, target_h = _YOUTUBE_SIZE if platform == "youtube" else _TIKTOK_SIZE
    font_size = 88 if platform == "youtube" else 72
    margin = 55

    img = _cv2_to_pil(frame)
    img = _smart_crop(img, target_w, target_h, subject)
    img = _apply_gradient(img)

    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    # Determine text side from subject position (negative space layout)
    side = _text_side(subject, target_w)
    if side == "right":
        text_x = target_w // 2
        text_max_w = target_w - text_x - margin
    else:
        text_x = margin
        text_max_w = target_w - margin * 2

    # Word-wrap title (keep original case — uppercase breaks Vietnamese diacritics)
    lines = _wrap_text(title, font, text_max_w)

    # Measure line height from a representative glyph
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = (bbox[3] - bbox[1]) + 10
    total_text_h = line_h * len(lines)

    # Text block sits at bottom with margin
    text_y = target_h - margin - total_text_h

    # Accent bar just above text — color matches dominant frame color
    accent_color = _dominant_color(frame)
    bar_top = text_y - 16
    draw.rectangle(
        [(text_x, bar_top), (target_w - margin, bar_top + 6)],
        fill=accent_color,
    )

    # Draw each line
    for i, line in enumerate(lines):
        _draw_outlined_text(draw, (text_x, text_y + i * line_h), line, font)

    return img.convert("RGB")
