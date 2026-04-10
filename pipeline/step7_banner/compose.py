"""Banner image composition using Pillow."""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# TikTok brand red — used as accent bar color
_ACCENT = (254, 44, 85)

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


def _smart_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Resize + center-crop to exact (w, h)."""
    src_ratio = img.width / img.height
    tgt_ratio = w / h
    if src_ratio > tgt_ratio:
        new_h, new_w = h, int(img.width * h / img.height)
    else:
        new_w, new_h = w, int(img.height * w / img.width)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


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


def compose_banner(frame: np.ndarray, title: str, platform: str) -> Image.Image:
    """Return a composed PIL Image banner for *platform* ('youtube' or 'tiktok')."""
    target_w, target_h = _YOUTUBE_SIZE if platform == "youtube" else _TIKTOK_SIZE
    font_size = 88 if platform == "youtube" else 72
    margin = 55

    img = _cv2_to_pil(frame)
    img = _smart_crop(img, target_w, target_h)
    img = _apply_gradient(img)

    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    # Word-wrap title to usable width (keep original case — uppercase breaks Vietnamese diacritics)
    lines = _wrap_text(title, font, target_w - margin * 2)

    # Measure line height from a representative glyph
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = (bbox[3] - bbox[1]) + 10
    total_text_h = line_h * len(lines)

    # Text block sits at bottom with margin
    text_y = target_h - margin - total_text_h

    # Accent bar just above text
    bar_top = text_y - 16
    draw.rectangle(
        [(margin, bar_top), (target_w - margin, bar_top + 6)],
        fill=_ACCENT,
    )

    # Draw each line
    for i, line in enumerate(lines):
        _draw_outlined_text(draw, (margin, text_y + i * line_h), line, font)

    return img.convert("RGB")
