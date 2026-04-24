"""Create overlay PNG with background image and intro text."""

import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Font paths (macOS, Linux, fallback)
FONT_PATHS = [
    "/System/Library/Fonts/Helvetica.ttc",  # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux
]


def _get_font(font_size: int) -> ImageFont.FreeTypeFont:
    """Get available TrueType font."""
    for font_path in FONT_PATHS:
        try:
            return ImageFont.truetype(font_path, font_size)
        except (IOError, OSError):
            continue

    logger.warning("No TrueType font found, using default")
    return ImageFont.load_default()


def _wrap_text(text: str, max_width: int = 35) -> str:
    """Wrap text to max width per line."""
    words = text.split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > max_width:
            if len(current_line) > 1:
                lines.append(" ".join(current_line[:-1]))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []

    if current_line:
        lines.append(" ".join(current_line))

    return "\n".join(lines)


def render_overlay(
    bg_image_path: Path,
    intro_text: str,
    output_path: Path,
    video_width: int = 1920,
    video_height: int = 1080,
) -> Path:
    """
    Create overlay PNG with background image and text.

    Args:
        bg_image_path: Path to background image
        intro_text: Vietnamese intro text
        output_path: Path to save overlay.png
        video_width: Video frame width (default 1920)
        video_height: Video frame height (default 1080)

    Returns:
        Path to overlay.png
    """
    # Load background image
    if not bg_image_path.exists():
        raise FileNotFoundError(f"Background image not found: {bg_image_path}")

    bg_img = Image.open(bg_image_path).convert("RGBA")

    # Image dimensions: 1/3 of video height
    overlay_height = video_height // 3  # 360 for 1080p
    overlay_width = video_width  # 1920

    # Resize background image to overlay dimensions (width × height)
    bg_resized = bg_img.resize((overlay_width, overlay_height), Image.Resampling.LANCZOS)

    # Create overlay with dark semi-transparent background
    overlay = Image.new("RGBA", (overlay_width, overlay_height), (0, 0, 0, 0))
    overlay.paste(bg_resized, (0, 0), bg_resized)

    # Add dark semi-transparent overlay for text readability
    # Create a dark overlay on the top half
    dark_overlay = Image.new("RGBA", (overlay_width, overlay_height // 2), (0, 0, 0, 180))
    overlay.paste(dark_overlay, (0, 0), dark_overlay)

    # Draw text on the overlay
    draw = ImageDraw.Draw(overlay)

    # Text positioning: top half of the image, centered
    font_size = 48
    font = _get_font(font_size)

    # Wrap text
    wrapped_text = _wrap_text(intro_text, max_width=35)

    # Get text bounding box to center it
    bbox = draw.textbbox((0, 0), wrapped_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Calculate position: centered horizontally, in top half
    text_x = (overlay_width - text_width) // 2
    text_y = (overlay_height // 2 - text_height) // 2 + 30  # offset for better visual

    # Draw text with white color
    draw.text((text_x, text_y), wrapped_text, fill=(255, 255, 255, 255), font=font)

    # Save as PNG
    overlay.save(output_path, "PNG")
    logger.info(f"Overlay saved: {output_path} ({overlay_width}×{overlay_height})")

    return output_path
