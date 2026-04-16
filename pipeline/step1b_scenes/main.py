"""
Step 1b: Scene detection — writes scenes.json to output_dir.

Primary:  ffmpeg scdet filter (always available)
Fallback: PySceneDetect AdaptiveDetector (optional, pip install "scenedetect>=0.6,<1.0")

Output:
  output/{video_id}/scenes.json     — cuts, scenes, detector, video_duration
  output/{video_id}/.step1b.done    — sentinel
"""

import json
import logging
import subprocess
from pathlib import Path

from pipeline.prereqs import check_prerequisites

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_video_duration(video_path: Path) -> float:
    """Return video duration in seconds via ffprobe. Returns 0.0 on failure."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        logger.warning("[step1b] ffprobe failed for %s", video_path)
        return 0.0
    try:
        return float(result.stdout.strip())
    except ValueError:
        logger.warning("[step1b] could not parse duration from ffprobe output")
        return 0.0


def _cuts_to_scenes(cuts: list[float], duration: float) -> list[tuple[float, float]]:
    """Convert a list of cut timestamps into (start, end) scene tuples."""
    boundaries = [0.0] + sorted(cuts)
    if duration > 0:
        boundaries.append(duration)
    scenes = []
    for i in range(len(boundaries) - 1):
        scenes.append((boundaries[i], boundaries[i + 1]))
    return scenes


def _detect_with_ffmpeg(video_path: Path) -> list[float]:
    """Detect scene cuts using ffmpeg scdet filter. Returns cut timestamps."""
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "scdet=threshold=10:sc_pass=1",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    cuts: list[float] = []
    for line in result.stderr.splitlines():
        if "lavfi.scd.time:" in line:
            # e.g. "  lavfi.scd.time:12.345678"
            for part in line.split():
                if part.startswith("lavfi.scd.time:"):
                    try:
                        cuts.append(float(part.split(":", 1)[1]))
                    except ValueError:
                        pass
    return sorted(set(cuts))


def _detect_with_pyscenedetect(video_path: Path) -> list[float]:
    """Fallback: detect scenes via PySceneDetect AdaptiveDetector."""
    from scenedetect import detect, AdaptiveDetector  # type: ignore
    scene_list = detect(str(video_path), AdaptiveDetector())
    cuts: list[float] = []
    for i, (_, end) in enumerate(scene_list):
        if i < len(scene_list) - 1:
            cuts.append(end.get_seconds())
    return sorted(cuts)


# ── Main ──────────────────────────────────────────────────────────────────────

def detect_scenes(output_dir: Path) -> Path:
    """Detect scene cuts in the source video and write scenes.json.

    Returns the path to scenes.json.
    """
    sentinel = output_dir / ".step1b.done"
    if sentinel.exists():
        print("[step1b] Skip — scenes.json already exists")
        return output_dir / "scenes.json"

    check_prerequisites("step1b_scenes", output_dir)

    # Find source video: first non-final .mp4 or .mkv
    video_path: Path | None = None
    for ext in ("*.mp4", "*.mkv"):
        for p in sorted(output_dir.glob(ext)):
            if not p.name.startswith("final_"):
                video_path = p
                break
        if video_path:
            break

    if video_path is None:
        raise FileNotFoundError(f"No source video found in {output_dir}")

    print(f"[step1b] Detecting scenes in {video_path.name} …")

    duration = _get_video_duration(video_path)
    if duration == 0.0:
        print("[step1b] WARNING: could not determine video duration")

    cuts = _detect_with_ffmpeg(video_path)
    detector = "ffmpeg_scdet"

    if not cuts:
        print("[step1b] ffmpeg scdet found 0 cuts — trying PySceneDetect fallback …")
        try:
            cuts = _detect_with_pyscenedetect(video_path)
            detector = "pyscenedetect_adaptive"
        except ImportError:
            print("[step1b] PySceneDetect not installed; install with: pip install 'scenedetect>=0.6,<1.0'")
        except Exception as exc:
            print(f"[step1b] PySceneDetect failed: {exc}")

    scenes = _cuts_to_scenes(cuts, duration)

    data = {
        "cuts": cuts,
        "scenes": [list(s) for s in scenes],
        "detector": detector,
        "video_duration": duration,
    }

    scenes_path = output_dir / "scenes.json"
    scenes_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    sentinel.touch()

    print(f"[step1b] Done — {len(cuts)} cut(s), {len(scenes)} scene(s) → {scenes_path}")
    return scenes_path
