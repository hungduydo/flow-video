"""Unit tests for api.flow_store.FlowStore"""
import pytest
from pathlib import Path

from api.flow_store import FlowStore

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


@pytest.fixture
def store(tmp_path):
    return FlowStore(db_path=tmp_path / "test_flows.db")


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_returns_flow_with_id(store):
    flow = store.create(name="My Flow", definition=_DEF)
    assert flow["id"]
    assert flow["name"] == "My Flow"
    assert flow["definition"]["url"] == _DEF["url"]
    assert flow["enabled"] is True
    assert flow["schedule"] is None


def test_create_with_schedule(store):
    flow = store.create(name="Scheduled", definition=_DEF, schedule="0 9 * * *")
    assert flow["schedule"] == "0 9 * * *"


# ── Get ───────────────────────────────────────────────────────────────────────

def test_get_returns_none_for_missing(store):
    assert store.get("nonexistent-id") is None


def test_get_returns_created_flow(store):
    created = store.create(name="Test", definition=_DEF)
    fetched = store.get(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_empty(store):
    assert store.list() == []


def test_list_returns_most_recent_first(store):
    a = store.create(name="A", definition=_DEF)
    b = store.create(name="B", definition=_DEF)
    flows = store.list()
    assert len(flows) == 2
    # Most recent (B) first
    assert flows[0]["id"] == b["id"]
    assert flows[1]["id"] == a["id"]


# ── Update ────────────────────────────────────────────────────────────────────

def test_update_name(store):
    flow = store.create(name="Old", definition=_DEF)
    updated = store.update(flow["id"], name="New")
    assert updated["name"] == "New"


def test_update_clears_schedule_when_set_to_none(store):
    flow = store.create(name="Scheduled", definition=_DEF, schedule="0 9 * * *")
    assert flow["schedule"] == "0 9 * * *"
    updated = store.update(flow["id"], schedule=None)
    assert updated["schedule"] is None


def test_update_unknown_field_is_ignored(store):
    flow = store.create(name="Test", definition=_DEF)
    # Passing an unrecognised field should not raise
    updated = store.update(flow["id"], nonexistent_field="value")
    assert updated["name"] == "Test"


def test_update_returns_none_for_missing_flow(store):
    # update on a missing ID returns None (no row matched, get returns None)
    result = store.update("no-such-id", name="Ghost")
    assert result is None


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_existing_flow(store):
    flow = store.create(name="Delete Me", definition=_DEF)
    assert store.delete(flow["id"]) is True
    assert store.get(flow["id"]) is None


def test_delete_nonexistent_returns_false(store):
    assert store.delete("does-not-exist") is False


# ── list_scheduled ────────────────────────────────────────────────────────────

def test_list_scheduled_only_returns_enabled_with_schedule(store):
    store.create(name="No schedule", definition=_DEF)
    store.create(name="Disabled", definition=_DEF, schedule="0 9 * * *", enabled=False)
    active = store.create(name="Active", definition=_DEF, schedule="0 10 * * *")
    scheduled = store.list_scheduled()
    assert len(scheduled) == 1
    assert scheduled[0]["id"] == active["id"]
