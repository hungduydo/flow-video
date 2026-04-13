"""Keyframe extraction and visual quality scoring for banner generation."""

import base64
import json
from pathlib import Path

import cv2
import numpy as np


def _frame_to_b64(frame: np.ndarray) -> str:
    """Encode an OpenCV BGR frame as a base64 JPEG string."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def save_llm_decision(
    review_dir: Path,
    chosen_frame_idx: int,
    title: str,
    video_title: str,
) -> None:
    """Save LLM decision metadata to frames review directory."""
    review_dir = Path(review_dir)
    metadata_path = review_dir / "candidates_metadata.json"

    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
    else:
        metadata = {"candidates": []}

    # Add/update LLM decision
    metadata["llm_decision"] = {
        "chosen_frame_index": chosen_frame_idx,
        "title": title,
        "video_title": video_title,
    }

    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"[frames] Saved LLM decision to {metadata_path}")

    # Generate HTML preview
    _generate_html_preview(review_dir, metadata)


def _generate_html_preview(review_dir: Path, metadata: dict) -> None:
    """Generate an HTML file to view all candidate frames and LLM decision."""
    review_dir = Path(review_dir)
    html_path = review_dir / "preview.html"

    candidates = metadata.get("candidates", [])
    llm_decision = metadata.get("llm_decision", {})
    chosen_idx = llm_decision.get("chosen_frame_index", -1)
    title = llm_decision.get("title", "N/A")
    video_title = llm_decision.get("video_title", "N/A")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Frame Candidates Preview</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }}
        .meta-info {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}
        .meta-item {{
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        .meta-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            font-weight: 600;
        }}
        .meta-value {{
            font-size: 16px;
            color: #333;
            margin-top: 5px;
            font-weight: 500;
        }}
        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }}
        .frame-card {{
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
            position: relative;
        }}
        .frame-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.2);
        }}
        .frame-card.selected {{
            border: 3px solid #04d9c4;
            transform: scale(1.05);
        }}
        .frame-image {{
            width: 100%;
            aspect-ratio: 16/9;
            object-fit: cover;
            background: #000;
        }}
        .frame-info {{
            padding: 15px;
        }}
        .frame-title {{
            font-size: 14px;
            font-weight: 600;
            color: #333;
            margin-bottom: 10px;
        }}
        .frame-score {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .score-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }}
        .score-bar {{
            flex: 1;
            height: 6px;
            background: #e0e0e0;
            border-radius: 3px;
            overflow: hidden;
        }}
        .score-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 3px;
        }}
        .selected-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: #04d9c4;
            color: white;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            color: white;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎬 Frame Candidates Preview</h1>
            <div class="meta-info">
                <div class="meta-item">
                    <div class="meta-label">Video Title</div>
                    <div class="meta-value">{video_title}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">LLM Selected Title</div>
                    <div class="meta-value">{title}</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Selected Frame Index</div>
                    <div class="meta-value">Frame #{chosen_idx} (of {len(candidates)})</div>
                </div>
                <div class="meta-item">
                    <div class="meta-label">Total Candidates</div>
                    <div class="meta-value">{len(candidates)} frames extracted</div>
                </div>
            </div>
        </header>
        <div class="gallery">
"""

    for candidate in candidates:
        idx = candidate.get("index", 0)
        filename = candidate.get("filename", "")
        score = candidate.get("score", 0)
        is_selected = idx == chosen_idx

        # Normalize score to 0-100 for visual bar
        score_pct = min(100, int(score * 100))

        selected_html = f'<div class="selected-badge">✓ SELECTED</div>' if is_selected else ""

        html_content += f"""            <div class="frame-card{' selected' if is_selected else ''}">
                {selected_html}
                <img src="{filename}" alt="Frame {idx}" class="frame-image">
                <div class="frame-info">
                    <div class="frame-title">Frame #{idx}</div>
                    <div class="frame-score">
                        <span class="score-label">Quality</span>
                        <div class="score-bar">
                            <div class="score-fill" style="width: {score_pct}%"></div>
                        </div>
                        <span style="font-size: 12px; color: #666; min-width: 40px;">{score:.3f}</span>
                    </div>
                </div>
            </div>
"""

    html_content += """        </div>
        <div class="footer">
            <p>💡 Compare frames visually with LLM's selection. All candidates ranked by quality score (brightness, contrast, colorfulness).</p>
        </div>
    </div>
</body>
</html>
"""

    html_path.write_text(html_content, encoding="utf-8")
    print(f"[frames] Generated preview: {html_path}")


def score_frame(frame: np.ndarray) -> float:
    """Score a frame on brightness, contrast, and colorfulness (0–1 each)."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Brightness: prefer frames near mid-range (not too dark/bright)
    mean = float(np.mean(gray))
    brightness = 1.0 - abs(mean - 128) / 128

    # Contrast: standard deviation of grayscale (higher = more texture)
    contrast = min(1.0, float(np.std(gray)) / 80.0)

    # Colorfulness: mean HSV saturation
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    colorfulness = float(np.mean(hsv[:, :, 1])) / 255.0

    return brightness * 0.25 + contrast * 0.35 + colorfulness * 0.40


def extract_candidates(
    video_path: Path,
    scenes_path: Path | None = None,
    max_candidates: int = 5,
    save_dir: Path | None = None,
) -> list[np.ndarray]:
    """Return up to *max_candidates* frames ranked by visual quality.

    Candidate timestamps come from:
      - Midpoints of each scene (from scenes.json, if present)
      - Evenly-spaced samples across the middle 60 % of the video

    If save_dir is provided, saves all candidate frames and metadata there.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps

    timestamps: list[float] = []

    # Scene midpoints — great visual variety across cuts
    if scenes_path and scenes_path.exists():
        data = json.loads(scenes_path.read_text())
        for scene in data.get("scenes", []):
            start, end = scene[0], scene[1]
            mid = (start + end) / 2
            if 10 < mid < duration_s - 10:
                timestamps.append(mid)

    # Evenly-spaced fallback samples (middle 60 %)
    start_s = duration_s * 0.20
    end_s = duration_s * 0.80
    n_samples = max(12, max_candidates * 3)
    for i in range(n_samples):
        t = start_s + i * (end_s - start_s) / max(n_samples - 1, 1)
        timestamps.append(t)

    # Deduplicate to nearest-second buckets, cap total reads at 20
    seen: set[int] = set()
    unique_ts: list[float] = []
    for t in timestamps:
        bucket = int(t)
        if bucket not in seen:
            seen.add(bucket)
            unique_ts.append(t)
    timestamps = unique_ts[:20]

    frames_scored: list[tuple[float, np.ndarray]] = []
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            frames_scored.append((score_frame(frame), frame))

    cap.release()

    frames_scored.sort(key=lambda x: x[0], reverse=True)
    top_frames = [f for _, f in frames_scored[:max_candidates]]

    # Save candidate frames and metadata if save_dir provided
    if save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        metadata = {"candidates": []}
        for idx, (score, frame) in enumerate(frames_scored[:max_candidates]):
            # Save frame as image
            frame_path = save_dir / f"frame_{idx:02d}_score_{score:.3f}.jpg"
            cv2.imwrite(str(frame_path), frame)

            # Add to metadata
            metadata["candidates"].append({
                "index": idx,
                "filename": f"frame_{idx:02d}_score_{score:.3f}.jpg",
                "score": round(float(score), 4),
                "timestamp": round(t if idx < len(frames_scored) else 0, 2),
            })

        # Save metadata
        metadata_path = save_dir / "candidates_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        print(f"[frames] Saved {len(top_frames)} candidate frames to {save_dir}")

    return top_frames
