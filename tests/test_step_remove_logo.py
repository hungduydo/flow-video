"""Unit tests for pipeline.step_remove_logo.main"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

# cv2 is an optional heavy dependency — stub it out at import time
# so the test module can be collected on machines without OpenCV installed.
_cv2_stub = ModuleType("cv2")
_cv2_stub.VideoCapture = MagicMock()
_cv2_stub.cvtColor = MagicMock(return_value=np.zeros((100, 100), dtype=np.float32))
_cv2_stub.GaussianBlur = MagicMock(return_value=np.zeros((100, 100), dtype=np.float32))
_cv2_stub.bitwise_or = MagicMock(return_value=np.zeros((100, 100), dtype=np.uint8))
_cv2_stub.dilate = MagicMock(return_value=np.zeros((100, 100), dtype=np.uint8))
_cv2_stub.imencode = MagicMock(return_value=(True, np.array([0], dtype=np.uint8)))
_cv2_stub.inpaint = MagicMock(return_value=np.zeros((100, 100, 3), dtype=np.uint8))
_cv2_stub.COLOR_BGR2GRAY = 6
_cv2_stub.CAP_PROP_FRAME_COUNT = 7
_cv2_stub.CAP_PROP_FRAME_WIDTH = 3
_cv2_stub.CAP_PROP_FRAME_HEIGHT = 4
_cv2_stub.CAP_PROP_FPS = 5
_cv2_stub.CAP_PROP_POS_FRAMES = 1
_cv2_stub.INPAINT_TELEA = 1
_cv2_stub.IMWRITE_JPEG_QUALITY = 1
sys.modules.setdefault("cv2", _cv2_stub)

from pipeline.step_remove_logo.main import (  # noqa: E402
    _corner_rects,
    _build_removal_filter,
    _bbox_for_corner,
    _save_detected_regions,
    detect_all_regions_llm,
    remove_logo,
)


# ── _corner_rects ─────────────────────────────────────────────────────────────

class TestCornerRects:
    def test_returns_four_corners(self):
        rects = _corner_rects(1920, 1080)
        assert set(rects.keys()) == {"top_left", "top_right", "bottom_left", "bottom_right"}

    def test_all_rects_have_four_values(self):
        rects = _corner_rects(1920, 1080)
        for v in rects.values():
            assert len(v) == 4

    def test_top_left_starts_at_origin(self):
        rects = _corner_rects(1920, 1080)
        x, y, w, h = rects["top_left"]
        assert x == 0
        assert y == 0

    def test_bottom_right_starts_at_correct_position(self):
        rects = _corner_rects(1920, 1080)
        x, y, w, h = rects["bottom_right"]
        assert x + w == 1920 or x > 0
        assert y + h == 1080 or y > 0

    def test_rects_are_positive_size(self):
        rects = _corner_rects(1920, 1080)
        for _, (x, y, w, h) in rects.items():
            assert w > 0
            assert h > 0

    def test_rects_within_frame(self):
        width, height = 1280, 720
        rects = _corner_rects(width, height)
        for _, (x, y, w, h) in rects.items():
            assert x >= 0
            assert y >= 0
            assert x + w <= width
            assert y + h <= height

    def test_scales_with_frame_dimensions(self):
        rects_hd = _corner_rects(1920, 1080)
        rects_4k = _corner_rects(3840, 2160)
        _, _, w_hd, h_hd = rects_hd["top_left"]
        _, _, w_4k, h_4k = rects_4k["top_left"]
        assert w_4k > w_hd
        assert h_4k > h_hd


# ── _build_removal_filter ─────────────────────────────────────────────────────

class TestBuildRemovalFilter:
    def test_returns_vf_flag(self):
        regions = [("top_left", 0, 0, 200, 100)]
        flag, _, _ = _build_removal_filter(regions, 1920, 1080)
        assert flag == "-vf"

    def test_filter_contains_delogo(self):
        regions = [("top_left", 0, 0, 200, 100)]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert "delogo" in filter_str

    def test_multiple_regions_chained(self):
        regions = [
            ("top_left", 0, 0, 200, 100),
            ("bottom_right", 1700, 950, 200, 100),
        ]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert filter_str.count("delogo") == 2

    def test_empty_extra_args(self):
        regions = [("top_left", 0, 0, 200, 100)]
        _, _, extra = _build_removal_filter(regions, 1920, 1080)
        assert extra == []

    def test_delogo_params_include_coordinates(self):
        regions = [("top_left", 50, 30, 200, 100)]
        _, filter_str, _ = _build_removal_filter(regions, 1920, 1080)
        assert "x=" in filter_str
        assert "y=" in filter_str
        assert "w=" in filter_str
        assert "h=" in filter_str


# ── remove_logo public API ────────────────────────────────────────────────────

class TestRemoveLogoApi:
    def test_raises_on_invalid_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        with pytest.raises(ValueError, match="quality"):
            remove_logo(video, quality="ultra")

    def test_raises_on_invalid_provider(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        with pytest.raises(ValueError, match="provider"):
            remove_logo(video, provider="magic")

    def test_default_output_path(self, tmp_path):
        video = tmp_path / "myvideo.mp4"
        video.touch()

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            import shutil
            with patch("shutil.copy2") as mock_copy:
                result = remove_logo(video)

        expected = tmp_path / "myvideo_clean.mp4"
        assert result == expected

    def test_copies_when_no_watermark(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            with patch("shutil.copy2") as mock_copy:
                remove_logo(video, out)

        mock_copy.assert_called_once_with(video, out)

    def test_calls_remove_fast_for_fast_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"
        regions = [("top_left", 0, 0, 200, 100)]

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=regions):
            with patch("pipeline.step_remove_logo.main._remove_fast") as mock_fast:
                mock_fast.return_value = None
                out.touch()  # simulate output created
                remove_logo(video, out, quality="fast")

        mock_fast.assert_called_once()

    def test_calls_remove_high_for_high_quality(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"
        regions = [("top_left", 0, 0, 200, 100)]

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=regions):
            with patch("pipeline.step_remove_logo.main._remove_high") as mock_high:
                mock_high.return_value = None
                out.touch()
                remove_logo(video, out, quality="high")

        mock_high.assert_called_once()

    def test_accepts_string_path(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.touch()

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            with patch("shutil.copy2"):
                result = remove_logo(str(video))

        assert isinstance(result, Path)


# ── _bbox_for_corner ─────────────────────────────────────────────────────────

class TestBboxForCorner:
    def _make_arrays(self, x_vals, y_vals):
        import numpy as np
        return np.array(x_vals), np.array(y_vals)

    def test_top_left_x_anchored_to_zero(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert x == 0

    def test_top_left_y_anchored_to_zero(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert y == 0

    def test_result_within_frame(self):
        import numpy as np
        xs, ys = np.array([10, 50]), np.array([5, 30])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        assert x >= 0
        assert y >= 0
        assert x + w <= 1920
        assert y + h <= 1080

    def test_minimum_size_enforced(self):
        import numpy as np
        # Very small mask should be expanded to minimum size
        xs, ys = np.array([5, 6]), np.array([5, 6])
        x, y, w, h = _bbox_for_corner("top_left", xs, ys, 0, 0, 300, 100, 1920, 1080)
        min_w = int(1920 * 0.10)
        min_h = int(1080 * 0.07)
        assert w >= min_w
        assert h >= min_h


# ── _save_detected_regions ────────────────────────────────────────────────────

class TestSaveDetectedRegions:
    def test_creates_json_file(self, tmp_path):
        _save_detected_regions(tmp_path, [], None)
        assert (tmp_path / "detected_regions.json").exists()

    def test_logos_written_correctly(self, tmp_path):
        import json
        logos = [("top_right", 10, 5, 100, 50), ("bottom_left", 0, 900, 80, 40)]
        _save_detected_regions(tmp_path, logos, None)
        data = json.loads((tmp_path / "detected_regions.json").read_text())
        assert len(data["logos"]) == 2
        assert data["logos"][0] == {"corner": "top_right", "x": 10, "y": 5, "w": 100, "h": 50}

    def test_subtitle_written_when_present(self, tmp_path):
        import json
        _save_detected_regions(tmp_path, [], (50, 950, 1820, 80))
        data = json.loads((tmp_path / "detected_regions.json").read_text())
        assert data["subtitle"] == {"x": 50, "y": 950, "w": 1820, "h": 80}

    def test_subtitle_is_null_when_none(self, tmp_path):
        import json
        _save_detected_regions(tmp_path, [], None)
        data = json.loads((tmp_path / "detected_regions.json").read_text())
        assert data["subtitle"] is None

    def test_empty_logos_list(self, tmp_path):
        import json
        _save_detected_regions(tmp_path, [], None)
        data = json.loads((tmp_path / "detected_regions.json").read_text())
        assert data["logos"] == []


# ── detect_all_regions_llm subtitle aggregation ───────────────────────────────

class TestDetectAllRegionsLlmSubtitle:
    def _make_cap(self, total_frames=10, width=1920, height=1080):
        import sys
        cv2 = sys.modules["cv2"]
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FRAME_COUNT: total_frames,
            cv2.CAP_PROP_FRAME_WIDTH:  width,
            cv2.CAP_PROP_FRAME_HEIGHT: height,
        }[prop]
        cap.read.return_value = (True, np.zeros((height, width, 3), dtype=np.uint8))
        return cap

    def _patch_cv2_cap(self, cap):
        import sys
        return patch.object(sys.modules["cv2"], "VideoCapture", return_value=cap)

    def test_subtitle_aggregation_min_x_avg_y_max_w_avg_h(self):
        """Verify min(x), avg(y), max(w), avg(h) + 10px pad."""
        import json as _json
        detections = [
            {"watermarks": [], "subtitle": {"detected": True,  "x": 0.10, "y": 0.80, "width": 0.80, "height": 0.05}},
            {"watermarks": [], "subtitle": {"detected": True,  "x": 0.05, "y": 0.85, "width": 0.90, "height": 0.06}},
        ]
        it = iter(detections)
        def fake_chat(msgs, model, base_url, api_key=None):
            return _json.dumps(next(it))

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step_remove_logo.main._ollama_chat", side_effect=fake_chat),
        ):
            _, subtitle = detect_all_regions_llm(
                Path("v.mp4"), n_frames=2,
                ollama_url="http://localhost", model="test",
            )

        assert subtitle is not None
        x, y, w, h = subtitle
        assert x == max(0, int(0.05 * 1920) - 10)           # min(x) - pad
        assert y == max(0, int(0.825 * 1080) - 10)          # avg(y) - pad
        assert w == min(1920 - x, int(0.90 * 1920) + 20)    # max(w) + 2*pad
        assert h == min(1080 - y, int(0.055 * 1080) + 20)   # avg(h) + 2*pad

    def test_subtitle_none_when_below_threshold(self):
        import json as _json
        call_count = 0
        def fake_chat(msgs, model, base_url, api_key=None):
            nonlocal call_count
            call_count += 1
            detected = call_count == 1
            return _json.dumps({"watermarks": [], "subtitle": {"detected": detected, "x": 0.1, "y": 0.8, "width": 0.8, "height": 0.05}})

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step_remove_logo.main._ollama_chat", side_effect=fake_chat),
        ):
            _, subtitle = detect_all_regions_llm(
                Path("v.mp4"), n_frames=5,
                ollama_url="http://localhost", model="test",
            )

        assert subtitle is None

    def test_logos_and_subtitle_returned_together(self):
        import json as _json
        response = {
            "watermarks": [{"corner": "top_right", "x": 0.9, "y": 0.0, "width": 0.05, "height": 0.05}],
            "subtitle": {"detected": True, "x": 0.05, "y": 0.85, "width": 0.90, "height": 0.06},
        }
        def fake_chat(msgs, model, base_url, api_key=None):
            return _json.dumps(response)

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step_remove_logo.main._ollama_chat", side_effect=fake_chat),
        ):
            logos, subtitle = detect_all_regions_llm(
                Path("v.mp4"), n_frames=3,
                ollama_url="http://localhost", model="test",
            )

        assert len(logos) == 1
        assert logos[0][0] == "top_right"
        assert subtitle is not None


# ── remove_logo saves detected_regions.json ──────────────────────────────────

class TestRemoveLogoSavesRegions:
    def test_saves_json_for_cv_provider(self, tmp_path):
        import json
        video = tmp_path / "test.mp4"
        video.touch()

        with patch("pipeline.step_remove_logo.main.detect_watermark_regions", return_value=[]):
            with patch("shutil.copy2"):
                remove_logo(video)

        regions_file = tmp_path / "detected_regions.json"
        assert regions_file.exists()
        data = json.loads(regions_file.read_text())
        assert "logos" in data
        assert "subtitle" in data

    def test_saves_subtitle_from_llm_provider(self, tmp_path):
        import json
        video = tmp_path / "test.mp4"
        video.touch()
        out = tmp_path / "out.mp4"

        logos = [("top_right", 10, 5, 100, 50)]
        subtitle = (50, 900, 1820, 80)

        with patch("pipeline.step_remove_logo.main.detect_all_regions_llm",
                   return_value=(logos, subtitle)):
            with patch("pipeline.step_remove_logo.main._remove_fast") as mock_fast:
                mock_fast.return_value = None
                out.touch()
                remove_logo(video, out, provider="llm")

        data = json.loads((tmp_path / "detected_regions.json").read_text())
        assert data["subtitle"] == {"x": 50, "y": 900, "w": 1820, "h": 80}
