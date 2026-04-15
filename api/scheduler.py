"""
scheduler.py — APScheduler wrapper for cron-based flow execution
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _HAS_APSCHEDULER = True
except ImportError:
    _HAS_APSCHEDULER = False

if TYPE_CHECKING:
    from .flow_store import FlowStore
    from .job_manager import JobManager
    from .models import JobCreateRequest

logger = logging.getLogger(__name__)


class FlowScheduler:
    """Thin wrapper around APScheduler BackgroundScheduler."""

    def __init__(self, flow_store: "FlowStore", job_manager: "JobManager"):
        self._store = flow_store
        self._jm = job_manager
        self._scheduler = BackgroundScheduler() if _HAS_APSCHEDULER else None
        self._running = False

    def start(self) -> None:
        if not _HAS_APSCHEDULER or self._scheduler is None:
            logger.warning("apscheduler not installed — scheduling disabled")
            return

        # Load all enabled+scheduled flows at startup
        for flow in self._store.list_scheduled():
            self._add_job(flow)

        self._scheduler.start()
        self._running = True
        logger.info("FlowScheduler started")

    def shutdown(self) -> None:
        if self._running and self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._running = False

    def sync_flow(self, flow: dict) -> None:
        """Add or update a scheduled job for the given flow dict."""
        if not _HAS_APSCHEDULER or self._scheduler is None:
            return
        flow_id = flow["id"]
        # Remove existing job (if any)
        if self._scheduler.get_job(flow_id):
            self._scheduler.remove_job(flow_id)
        # Add new job only if enabled + has schedule
        if flow.get("enabled") and flow.get("schedule"):
            self._add_job(flow)

    def remove_flow(self, flow_id: str) -> None:
        if not _HAS_APSCHEDULER or self._scheduler is None:
            return
        if self._scheduler.get_job(flow_id):
            self._scheduler.remove_job(flow_id)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_job(self, flow: dict) -> None:
        from .models import JobCreateRequest

        flow_id = flow["id"]
        try:
            trigger = CronTrigger.from_crontab(flow["schedule"])
        except Exception as exc:
            logger.warning("Invalid cron for flow %s: %s", flow_id, exc)
            return

        definition = flow["definition"]
        # Ensure it's a dict (already deserialized by flow_store)
        req = JobCreateRequest(**definition) if isinstance(definition, dict) else definition

        self._scheduler.add_job(
            func=self._run_flow,
            trigger=trigger,
            id=flow_id,
            name=flow.get("name", flow_id),
            kwargs={"request": req},
            replace_existing=True,
        )
        logger.info("Scheduled flow '%s' (%s) with cron '%s'", flow.get("name"), flow_id, flow["schedule"])

    def _run_flow(self, request: "JobCreateRequest") -> None:
        job = self._jm.submit(request)
        logger.info("Scheduler triggered job %s", job.job_id)
