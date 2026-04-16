"""Integration tests for the /flows API endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from pathlib import Path

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
def client(tmp_path):
    """Create a TestClient with an isolated FlowStore pointing at a temp DB."""
    from api.flow_store import FlowStore
    from api.scheduler import FlowScheduler
    from api.app import create_app

    with patch("api.app.FlowStore") as MockStore, \
         patch("api.app.FlowScheduler") as MockSched, \
         patch("api.app.JobManager") as MockJM:

        real_store = FlowStore(db_path=tmp_path / "test.db")
        MockStore.return_value = real_store

        mock_sched = MagicMock(spec=FlowScheduler)
        MockSched.return_value = mock_sched

        mock_jm = MagicMock()
        mock_jm.list_jobs.return_value = []
        MockJM.return_value = mock_jm

        app = create_app()
        yield TestClient(app, raise_server_exceptions=True)


# ── POST /flows ───────────────────────────────────────────────────────────────

def test_create_flow_success(client):
    resp = client.post("/flows", json={"name": "My Flow", "definition": _DEF, "enabled": True})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Flow"
    assert body["id"]


def test_create_flow_invalid_cron_returns_422(client):
    resp = client.post("/flows", json={
        "name": "Bad Schedule",
        "definition": _DEF,
        "schedule": "every tuesday",
        "enabled": True,
    })
    assert resp.status_code == 422
    assert "Invalid cron" in resp.json()["detail"]


def test_create_flow_valid_cron_accepted(client):
    resp = client.post("/flows", json={
        "name": "Morning Run",
        "definition": _DEF,
        "schedule": "0 9 * * *",
        "enabled": True,
    })
    assert resp.status_code == 201
    assert resp.json()["schedule"] == "0 9 * * *"


# ── GET /flows ────────────────────────────────────────────────────────────────

def test_list_flows_empty(client):
    resp = client.get("/flows")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_flows_returns_created(client):
    client.post("/flows", json={"name": "Flow A", "definition": _DEF, "enabled": True})
    resp = client.get("/flows")
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "Flow A"


# ── GET /flows/{id} ───────────────────────────────────────────────────────────

def test_get_flow_not_found(client):
    resp = client.get("/flows/no-such-id")
    assert resp.status_code == 404


def test_get_flow_success(client):
    created = client.post("/flows", json={"name": "Test", "definition": _DEF, "enabled": True}).json()
    resp = client.get(f"/flows/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


# ── PATCH /flows/{id} ────────────────────────────────────────────────────────

def test_patch_flow_name(client):
    created = client.post("/flows", json={"name": "Old Name", "definition": _DEF, "enabled": True}).json()
    resp = client.patch(f"/flows/{created['id']}", json={"name": "New Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_patch_flow_clears_schedule(client):
    """Explicit null schedule must clear the schedule (model_fields_set fix)."""
    created = client.post("/flows", json={
        "name": "Scheduled",
        "definition": _DEF,
        "schedule": "0 9 * * *",
        "enabled": True,
    }).json()
    assert created["schedule"] == "0 9 * * *"

    resp = client.patch(f"/flows/{created['id']}", json={"schedule": None})
    assert resp.status_code == 200
    assert resp.json()["schedule"] is None


def test_patch_flow_invalid_cron_returns_422(client):
    created = client.post("/flows", json={"name": "F", "definition": _DEF, "enabled": True}).json()
    resp = client.patch(f"/flows/{created['id']}", json={"schedule": "not a cron"})
    assert resp.status_code == 422


def test_patch_flow_not_found(client):
    resp = client.patch("/flows/ghost-id", json={"name": "X"})
    assert resp.status_code == 404


# ── DELETE /flows/{id} ───────────────────────────────────────────────────────

def test_delete_flow_success(client):
    created = client.post("/flows", json={"name": "To Delete", "definition": _DEF, "enabled": True}).json()
    resp = client.delete(f"/flows/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True
    # Confirm it's gone
    assert client.get(f"/flows/{created['id']}").status_code == 404


def test_delete_flow_not_found(client):
    resp = client.delete("/flows/nonexistent")
    assert resp.status_code == 404
