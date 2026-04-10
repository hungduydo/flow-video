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
) -> list[np.ndarray]:
    """Return up to *max_candidates* frames ranked by visual quality.

    Candidate timestamps come from:
      - Midpoints of each scene (from scenes.json, if present)
      - Evenly-spaced samples across the middle 60 % of the video
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
    return [f for _, f in frames_scored[:max_candidates]]
