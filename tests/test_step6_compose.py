"""Unit tests for pipeline.step6_compose"""

import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

# Stub cv2 before any import that pulls it in
_cv2_stub = ModuleType("cv2")
_cv2_stub.VideoCapture = MagicMock()
_cv2_stub.imencode = MagicMock(return_value=(True, np.array([0], dtype=np.uint8)))
_cv2_stub.CAP_PROP_FRAME_COUNT = 7
_cv2_stub.CAP_PROP_FRAME_WIDTH = 3
_cv2_stub.CAP_PROP_FRAME_HEIGHT = 4
_cv2_stub.CAP_PROP_POS_FRAMES = 1
_cv2_stub.IMWRITE_JPEG_QUALITY = 1
sys.modules.setdefault("cv2", _cv2_stub)

from pipeline.step6_compose.main import (  # noqa: E402
    _get_tiktok_crop,
    _compose_one,
    _SUBTITLE_FORCE_STYLE,
)
from pipeline.step6_compose.detect_subtitle import detect_subtitle_region  # noqa: E402


# ── _SUBTITLE_FORCE_STYLE ────────────────────────────────────────────────────

class TestSubtitleForceStyle:
    def test_all_combinations_defined(self):
        for platform in ("youtube", "tiktok"):
            for pos in ("bottom", "top"):
                assert (platform, pos) in _SUBTITLE_FORCE_STYLE

    def test_bottom_uses_alignment_2(self):
        assert "Alignment=2" in _SUBTITLE_FORCE_STYLE[("youtube", "bottom")]
        assert "Alignment=2" in _SUBTITLE_FORCE_STYLE[("tiktok", "bottom")]

    def test_top_uses_alignment_8(self):
        assert "Alignment=8" in _SUBTITLE_FORCE_STYLE[("youtube", "top")]
        assert "Alignment=8" in _SUBTITLE_FORCE_STYLE[("tiktok", "top")]

    def test_tiktok_bottom_has_higher_margin_than_youtube(self):
        def margin_v(key):
            for part in _SUBTITLE_FORCE_STYLE[key].split(","):
                if part.startswith("MarginV="):
                    return int(part.split("=")[1])
            return 0

        assert margin_v(("tiktok", "bottom")) > margin_v(("youtube", "bottom"))


# ── _get_tiktok_crop ─────────────────────────────────────────────────────────

class TestGetTiktokCrop:
    def test_center_crop_default(self):
        result = _get_tiktok_crop(1920, 1080)
        target_w = int(1080 * 9 / 16)      # 607
        x_offset = (1920 - target_w) // 2  # 656
        assert result == f"crop={target_w}:1080:{x_offset}:0"

    def test_custom_crop_x(self):
        result = _get_tiktok_crop(1920, 1080, crop_x=100)
        target_w = int(1080 * 9 / 16)
        assert result == f"crop={target_w}:1080:100:0"

    def test_crop_x_clamped_to_zero(self):
        result = _get_tiktok_crop(1920, 1080, crop_x=-50)
        target_w = int(1080 * 9 / 16)
        assert result == f"crop={target_w}:1080:0:0"

    def test_crop_x_clamped_to_max(self):
        target_w = int(1080 * 9 / 16)
        max_x = 1920 - target_w
        result = _get_tiktok_crop(1920, 1080, crop_x=9999)
        assert result == f"crop={target_w}:1080:{max_x}:0"


# ── _compose_one vf chain ────────────────────────────────────────────────────

class TestComposeOneVfChain:
    """Verify _compose_one builds the correct ffmpeg -vf argument."""

    def _run(self, **kwargs):
        """Call _compose_one and capture the ffmpeg command."""
        captured = {}

        def fake_run(cmd, **_):
            captured["cmd"] = cmd
            result = MagicMock()
            result.returncode = 0
            return result

        defaults = dict(
            video_path=Path("v.mp4"),
            audio_path=Path("a.mp3"),
            srt_path=Path("/tmp/captions_vn.srt"),
            final_path=Path("out.mp4"),
            crf=23,
        )
        defaults.update(kwargs)

        with patch("pipeline.step6_compose.main.subprocess.run", side_effect=fake_run):
            _compose_one(**defaults)

        vf_idx = captured["cmd"].index("-vf") + 1
        return captured["cmd"][vf_idx]

    def test_default_vf_contains_scale_and_crop(self):
        vf = self._run()
        assert "scale=iw*1.05:ih*1.05" in vf
        assert "crop=iw/1.05:ih/1.05" in vf

    def test_default_vf_ends_with_subtitles(self):
        vf = self._run()
        # force_style contains a comma so we can't split naively —
        # just verify subtitles= appears after the crop filter
        assert "subtitles=" in vf
        assert vf.index("subtitles=") > vf.index("crop=")

    def test_delogo_applied_before_scale(self):
        vf = self._run(delogo_region=(10, 20, 300, 50))
        parts = vf.split(",")
        idx_delogo = next(i for i, p in enumerate(parts) if p.startswith("delogo="))
        idx_scale  = next(i for i, p in enumerate(parts) if p.startswith("scale="))
        assert idx_delogo < idx_scale

    def test_delogo_uses_correct_coords(self):
        vf = self._run(delogo_region=(10, 20, 300, 50))
        assert "delogo=x=10:y=20:w=300:h=50" in vf

    def test_no_delogo_when_region_is_none(self):
        vf = self._run(delogo_region=None)
        assert "delogo" not in vf

    def test_extra_vf_inserted_before_subtitles(self):
        vf = self._run(extra_vf="crop=607:1080:656:0")
        parts = vf.split(",")
        idx_extra    = next(i for i, p in enumerate(parts) if "607" in p)
        idx_subtitles = next(i for i, p in enumerate(parts) if p.startswith("subtitles="))
        assert idx_extra < idx_subtitles


# ── detect_subtitle_region aggregation ───────────────────────────────────────

class TestDetectSubtitleRegionAggregation:
    """Test the aggregation logic: min(x), avg(y), max(w), avg(h) + 10px pad."""

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
        """Patch cv2.VideoCapture on the module that detect_subtitle.py actually imports."""
        import sys
        return patch.object(sys.modules["cv2"], "VideoCapture", return_value=cap)

    def test_aggregation_min_x_avg_y_max_w_avg_h(self):
        """Two detections: aggregate and verify pixel conversion + 10px pad."""
        detections = [
            {"detected": True, "x": 0.1, "y": 0.8, "width": 0.8, "height": 0.05},
            {"detected": True, "x": 0.05, "y": 0.85, "width": 0.9, "height": 0.06},
        ]
        responses = iter(detections)

        def fake_chat(messages, model, base_url, api_key=None):
            import json
            d = next(responses)
            return json.dumps({"subtitle": d})

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step6_compose.detect_subtitle._ollama_chat", side_effect=fake_chat),
        ):
            result = detect_subtitle_region(
                Path("v.mp4"), n_frames=2,
                ollama_url="http://localhost", model="test",
            )

        assert result is not None
        x, y, w, h = result

        # min(x): min(0.1, 0.05) = 0.05 → 0.05*1920 = 96 - 10 pad = 86
        assert x == max(0, int(0.05 * 1920) - 10)
        # avg(y): (0.8+0.85)/2 = 0.825 → 0.825*1080 = 891 - 10 pad = 881
        assert y == max(0, int(0.825 * 1080) - 10)
        # max(w): max(0.8, 0.9) = 0.9 → 0.9*1920 = 1728 + 20 pad
        assert w == min(1920 - x, int(0.9 * 1920) + 20)
        # avg(h): (0.05+0.06)/2 = 0.055 → 0.055*1080 = 59 + 20 pad
        assert h == min(1080 - y, int(0.055 * 1080) + 20)

    def test_returns_none_when_below_threshold(self):
        """Only 1 out of 5 frames detects a subtitle → below majority → None."""
        call_count = 0

        def fake_chat(messages, model, base_url, api_key=None):
            import json
            nonlocal call_count
            call_count += 1
            detected = call_count == 1  # only first frame detects
            return json.dumps({"subtitle": {"detected": detected, "x": 0.1, "y": 0.8, "width": 0.8, "height": 0.05}})

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step6_compose.detect_subtitle._ollama_chat", side_effect=fake_chat),
        ):
            result = detect_subtitle_region(
                Path("v.mp4"), n_frames=5,
                ollama_url="http://localhost", model="test",
            )

        assert result is None

    def test_bad_json_is_skipped(self):
        """Malformed LLM responses are silently skipped."""
        def fake_chat(messages, model, base_url, api_key=None):
            return "not json at all"

        cap = self._make_cap()
        with (
            self._patch_cv2_cap(cap),
            patch("pipeline.step6_compose.detect_subtitle._ollama_chat", side_effect=fake_chat),
        ):
            result = detect_subtitle_region(
                Path("v.mp4"), n_frames=3,
                ollama_url="http://localhost", model="test",
            )

        assert result is None


# ── compose() reads detected_regions.json ────────────────────────────────────

class TestComposeReadsDetectedRegions:
    """compose(subtitle_position='auto') reads detected_regions.json first."""

    def _make_output_dir(self, tmp_path):
        d = tmp_path / "BV1xxx"
        d.mkdir()
        (d / "original.mp4").touch()
        (d / "audio_vn_full.mp3").touch()
        (d / "captions_vn.srt").touch()
        return d

    def test_reads_subtitle_from_json_file(self, tmp_path):
        import json
        output_dir = self._make_output_dir(tmp_path)
        regions_file = output_dir / "detected_regions.json"
        regions_file.write_text(json.dumps({
            "logos": [],
            "subtitle": {"x": 50, "y": 900, "w": 1820, "h": 80},
        }))

        from pipeline.step6_compose.main import compose
        ffmpeg_calls = []

        def fake_run(cmd, **_):
            ffmpeg_calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            (output_dir / "final_youtube.mp4").touch()
            return r

        def fake_ffprobe(cmd, **_):
            r = MagicMock()
            r.returncode = 0
            r.stdout = "1920,1080\n"
            return r

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return fake_ffprobe(cmd, **kwargs)
            return fake_run(cmd, **kwargs)

        with patch("pipeline.step6_compose.main.subprocess.run", side_effect=side_effect):
            compose(output_dir, subtitle_position="auto")

        # subtitle at y=900 in 1080p → vertical centre 940 > 540 → subtitles at top
        vf = next(
            cmd[cmd.index("-vf") + 1]
            for cmd in ffmpeg_calls
            if "-vf" in cmd
        )
        assert "Alignment=8" in vf          # top position
        assert "delogo=x=50:y=900" in vf    # delogo applied

    def test_falls_back_to_llm_when_no_json(self, tmp_path):
        output_dir = self._make_output_dir(tmp_path)

        from pipeline.step6_compose.main import compose

        fallback_called = []

        def fake_detect(video_path, **kwargs):
            fallback_called.append(True)
            return None  # no subtitle found

        def fake_run(cmd, **_):
            r = MagicMock()
            r.returncode = 0
            (output_dir / "final_youtube.mp4").touch()
            return r

        def side_effect(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                r = MagicMock(); r.returncode = 0; r.stdout = "1920,1080\n"
                return r
            return fake_run(cmd, **kwargs)

        with (
            patch("pipeline.step6_compose.main.subprocess.run", side_effect=side_effect),
            patch("pipeline.step6_compose.detect_subtitle.detect_subtitle_region",
                  side_effect=fake_detect),
        ):
            compose(output_dir, subtitle_position="auto")

        assert fallback_called, "Should fall back to LLM when detected_regions.json absent"
