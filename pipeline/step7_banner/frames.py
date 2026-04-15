"""Keyframe extraction, visual quality scoring, and subject detection for banner generation."""

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

    metadata["llm_decision"] = {
        "chosen_frame_index": chosen_frame_idx,
        "title": title,
        "video_title": video_title,
    }

    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"[frames] Saved LLM decision to {metadata_path}")

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
        .subject-badge {{
            position: absolute;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.6);
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
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
        subject = candidate.get("subject_info")
        is_selected = idx == chosen_idx

        score_pct = min(100, int(score * 100))
        selected_html = '<div class="selected-badge">✓ SELECTED</div>' if is_selected else ""

        subject_label = ""
        if subject:
            stype = subject.get("type", "")
            subject_label = f'<div class="subject-badge">{"👤 face" if stype == "face" else "👁 saliency"}</div>'

        html_content += f"""            <div class="frame-card{' selected' if is_selected else ''}">
                {selected_html}
                {subject_label}
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


def _laplacian_sharpness(frame: np.ndarray) -> float:
    """Return the Laplacian variance of a frame — higher = sharper."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def detect_subject(frame: np.ndarray) -> dict | None:
    """Detect the primary subject in a frame.

    Returns a dict with subject info (pixel coordinates), or None.

    Priority:
      1. MediaPipe FaceDetection — returns {"type": "face", "x", "y", "w", "h", "eye_y", "cx", "cy"}
      2. OpenCV saliency map fallback — returns {"type": "saliency", "cx", "cy"}
    """
    h, w = frame.shape[:2]

    # ── 1. Try MediaPipe face detection ──────────────────────────────────────
    try:
        import mediapipe as mp
        mp_face = mp.solutions.face_detection
        with mp_face.FaceDetection(model_selection=0, min_detection_confidence=0.5) as detector:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = detector.process(rgb)
            if results.detections:
                # Take the detection with highest confidence
                best = max(results.detections, key=lambda d: d.score[0])
                bb = best.location_data.relative_bounding_box
                fx = int(bb.xmin * w)
                fy = int(bb.ymin * h)
                fw = int(bb.width * w)
                fh = int(bb.height * h)
                cx = fx + fw // 2
                cy = fy + fh // 2

                # Eye y: use right-eye keypoint (index 0) if available
                eye_y = cy
                kps = best.location_data.relative_keypoints
                if kps:
                    eye_y = int(kps[0].y * h)

                return {
                    "type": "face",
                    "x": fx, "y": fy, "w": fw, "h": fh,
                    "cx": cx, "cy": cy,
                    "eye_y": eye_y,
                }
    except Exception:
        pass  # mediapipe unavailable or failed — fall through

    # ── 2. Fallback: OpenCV saliency map ─────────────────────────────────────
    try:
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, sal_map = saliency.computeSaliency(frame)
        if ok:
            sal_map = (sal_map * 255).astype(np.uint8)
            _, thresh = cv2.threshold(sal_map, 128, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
                mx, my, mw, mh = cv2.boundingRect(largest)
                return {
                    "type": "saliency",
                    "cx": mx + mw // 2,
                    "cy": my + mh // 2,
                }
    except Exception:
        pass

    return None


def score_frame(frame: np.ndarray) -> float:
    """Score a frame on sharpness, brightness, contrast, and colorfulness (0–1).

    Returns 0.0 immediately for blurry frames (Laplacian variance < 100).
    """
    if _laplacian_sharpness(frame) < 100:
        return 0.0

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
    sample_interval: float = 1.0,
) -> list[tuple[np.ndarray, dict | None]]:
    """Return up to *max_candidates* (frame, subject_info) pairs ranked by visual quality.

    Samples one frame every *sample_interval* seconds (default 1s) across the
    middle 60 % of the video. Blurry frames (Laplacian variance < 100) score 0
    and are excluded from the top-N selection.

    Args:
        video_path:       Path to the video file.
        scenes_path:      Optional path to scenes.json (unused for sampling,
                          kept for API compatibility).
        max_candidates:   Maximum number of top frames to return.
        save_dir:         If given, candidate frames + metadata are saved here.
        sample_interval:  Seconds between samples (0.5 for dense, 1.0 default).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps

    # Sample across the middle 60 % to avoid intros/outros
    start_s = duration_s * 0.20
    end_s = duration_s * 0.80

    timestamps: list[float] = []
    t = start_s
    while t <= end_s:
        timestamps.append(t)
        t += sample_interval

    # Read all frames at each timestamp
    all_frames: list[tuple[float, float, np.ndarray]] = []  # (timestamp, score, frame)
    for t in timestamps:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if ok:
            all_frames.append((t, score_frame(frame), frame))

    cap.release()

    total_sampled = len(all_frames)
    sharp_count = sum(1 for _, s, _ in all_frames if s > 0)
    print(f"[frames] Sampled {total_sampled} frames at {sample_interval}s interval "
          f"({sharp_count} sharp, {total_sampled - sharp_count} blurry filtered)")

    # Sort by score descending; top-N are the candidates passed to LLM
    all_frames.sort(key=lambda x: x[1], reverse=True)
    top_scored = all_frames[:max_candidates]
    top_timestamps = {t for t, _, _ in top_scored}

    # Detect subject for each top frame
    results: list[tuple[np.ndarray, dict | None]] = []
    for _t, _score, frame in top_scored:
        subject = detect_subject(frame)
        results.append((frame, subject))

    # Save ALL scanned frames + metadata if save_dir provided
    if save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Map top-frame positions for O(1) lookup
        top_indices = {i for i, (t, _, _) in enumerate(all_frames) if t in top_timestamps}

        metadata: dict = {"candidates": [], "all_frames": []}
        candidate_counter = 0

        for scan_idx, (t, score, frame) in enumerate(all_frames):
            is_candidate = scan_idx in top_indices
            filename = f"scan_{scan_idx:04d}_t{t:.1f}s_score_{score:.3f}.jpg"
            cv2.imwrite(str(save_dir / filename), frame)

            entry = {
                "scan_index": scan_idx,
                "timestamp_s": round(t, 2),
                "filename": filename,
                "score": round(float(score), 4),
                "is_candidate": is_candidate,
                "blurry": score == 0.0,
            }
            metadata["all_frames"].append(entry)

            if is_candidate:
                subject = results[candidate_counter][1]
                cand_entry = {
                    "index": candidate_counter,
                    "filename": filename,
                    "score": round(float(score), 4),
                    "subject_info": subject,
                }
                metadata["candidates"].append(cand_entry)
                candidate_counter += 1

        metadata_path = save_dir / "candidates_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
        print(f"[frames] Saved {total_sampled} scanned frames to {save_dir} "
              f"(top {len(results)} candidates marked)")

    return results
