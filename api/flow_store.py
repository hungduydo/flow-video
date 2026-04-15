"""
flow_store.py — SQLite-backed CRUD for flow definitions
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).parent.parent / "flows.db"

_DDL = """
CREATE TABLE IF NOT EXISTS flows (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    definition TEXT NOT NULL,
    schedule   TEXT,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["definition"] = json.loads(d["definition"])
    d["enabled"] = bool(d["enabled"])
    return d


class FlowStore:
    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_DDL)
        self._conn.commit()

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def create(self, name: str, definition: dict, schedule: Optional[str] = None, enabled: bool = True) -> dict:
        flow_id = str(uuid.uuid4())
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO flows (id, name, definition, schedule, enabled, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (flow_id, name, json.dumps(definition), schedule, int(enabled), now, now),
            )
            self._conn.commit()
        return self.get(flow_id)  # type: ignore[return-value]

    def get(self, flow_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM flows WHERE id = ?", (flow_id,)).fetchone()
        return _row_to_dict(row) if row else None

    def list(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM flows ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]

    def update(self, flow_id: str, **fields) -> Optional[dict]:
        allowed = {"name", "definition", "schedule", "enabled"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get(flow_id)

        if "definition" in updates:
            updates["definition"] = json.dumps(updates["definition"])
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])

        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [flow_id]

        with self._lock:
            self._conn.execute(f"UPDATE flows SET {set_clause} WHERE id = ?", values)
            self._conn.commit()
        return self.get(flow_id)

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM flows WHERE id = ?", (flow_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def list_scheduled(self) -> list[dict]:
        """Return flows that have a schedule and are enabled."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM flows WHERE schedule IS NOT NULL AND enabled = 1"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
