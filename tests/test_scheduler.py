"""Unit tests for api.scheduler.FlowScheduler"""
import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def scheduler():
    from api.flow_store import FlowStore
    from api.job_manager import JobManager
    from api.scheduler import FlowScheduler

    mock_store = MagicMock(spec=FlowStore)
    mock_store.list_scheduled.return_value = []
    mock_jm = MagicMock(spec=JobManager)

    with patch("api.scheduler._HAS_APSCHEDULER", True), \
         patch("api.scheduler.BackgroundScheduler") as MockSched:
        mock_bg = MagicMock()
        MockSched.return_value = mock_bg
        sched = FlowScheduler(flow_store=mock_store, job_manager=mock_jm)
        sched.start()
        yield sched, mock_bg


_DEF = {
    "url": "https://www.bilibili.com/video/BV1xx411",
    "cookies_file": None,
    "model": "large-v3",
    "transcriber": "whisper",
    "translator": "gemini",
    "tts_provider": "edge_tts",
    "platform": "youtube",
    "show_subtitle": True,
    "crf": 23,
    "tiktok_crop_x": None,
    "from_step": None,
    "force": False,
    "output_dir": "output",
}

_FLOW = {
    "id": "flow-123",
    "name": "Test Flow",
    "definition": _DEF,
    "schedule": "0 9 * * *",
    "enabled": True,
}


# ── sync_flow ─────────────────────────────────────────────────────────────────

def test_sync_flow_adds_job_for_enabled_scheduled_flow(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = None  # no existing job

    sched.sync_flow(_FLOW)

    mock_bg.add_job.assert_called_once()
    call_kwargs = mock_bg.add_job.call_args.kwargs
    assert call_kwargs["id"] == "flow-123"
    assert call_kwargs["replace_existing"] is True


def test_sync_flow_removes_existing_job_before_adding(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = MagicMock()  # existing job present

    sched.sync_flow(_FLOW)

    mock_bg.remove_job.assert_called_once_with("flow-123")
    mock_bg.add_job.assert_called_once()


def test_sync_flow_disabled_flow_removes_job(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = MagicMock()

    disabled_flow = {**_FLOW, "enabled": False}
    sched.sync_flow(disabled_flow)

    mock_bg.remove_job.assert_called_once_with("flow-123")
    mock_bg.add_job.assert_not_called()


def test_sync_flow_no_schedule_removes_job(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = MagicMock()

    unscheduled_flow = {**_FLOW, "schedule": None}
    sched.sync_flow(unscheduled_flow)

    mock_bg.remove_job.assert_called_once_with("flow-123")
    mock_bg.add_job.assert_not_called()


def test_sync_flow_invalid_cron_logs_warning_and_skips(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = None

    bad_flow = {**_FLOW, "schedule": "not a cron"}
    sched.sync_flow(bad_flow)  # must not raise

    mock_bg.add_job.assert_not_called()


# ── remove_flow ───────────────────────────────────────────────────────────────

def test_remove_flow_calls_remove_job(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = MagicMock()

    sched.remove_flow("flow-123")

    mock_bg.remove_job.assert_called_once_with("flow-123")


def test_remove_flow_noop_if_not_scheduled(scheduler):
    sched, mock_bg = scheduler
    mock_bg.get_job.return_value = None

    sched.remove_flow("flow-123")  # must not raise

    mock_bg.remove_job.assert_not_called()


# ── shutdown ──────────────────────────────────────────────────────────────────

def test_shutdown_calls_scheduler_shutdown(scheduler):
    sched, mock_bg = scheduler
    sched.shutdown()
    mock_bg.shutdown.assert_called_once_with(wait=False)
    assert sched._running is False
