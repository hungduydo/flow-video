"""
app.py — flow-video REST API
============================
Run with:  python -m api
"""
from __future__ import annotations

import asyncio
import json
import os

# Must be set before any pipeline module is imported (gRPC fork-safety)
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "1")
os.environ.setdefault("GRPC_POLL_STRATEGY", "poll")

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .flow_store import FlowStore
from .job_manager import JobManager, OUTPUT_FILES
from .models import (
    FileListResponse,
    FlowCreateRequest,
    FlowResponse,
    FlowUpdateRequest,
    HealthResponse,
    JobCreateRequest,
    JobResponse,
    LogsResponse,
    RetryRequest,
)
from .pipeline_runner import run_job
from .scheduler import FlowScheduler

load_dotenv()

# ── App factory ───────────────────────────────────────────────────────────────

def _make_job_response(job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        video_id=job.video_id,
        current_step=job.current_step,
        current_step_name=job.current_step_name,
        failed_step=job.failed_step,
        failed_step_name=job.failed_step_name,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        output_files=job.output_files(),
        request=job.request,
    )


def _make_flow_response(flow: dict) -> FlowResponse:
    return FlowResponse(
        id=flow["id"],
        name=flow["name"],
        definition=JobCreateRequest(**flow["definition"]),
        schedule=flow["schedule"],
        enabled=flow["enabled"],
        created_at=flow["created_at"],
        updated_at=flow["updated_at"],
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="flow-video API",
        description="REST API for the flow-video Bilibili → Vietnamese dubbing pipeline",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    max_workers = int(os.getenv("API_MAX_WORKERS", "2"))
    job_manager = JobManager(max_workers=max_workers)
    job_manager.set_runner(run_job)
    app.state.job_manager = job_manager

    flow_store = FlowStore()
    app.state.flow_store = flow_store

    scheduler = FlowScheduler(flow_store=flow_store, job_manager=job_manager)
    app.state.scheduler = scheduler
    scheduler.start()

    @app.on_event("shutdown")
    def _shutdown():
        scheduler.shutdown()
        job_manager.shutdown()

    # ── Health ────────────────────────────────────────────────────────────────

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    def health():
        jm: JobManager = app.state.job_manager
        with jm._lock:
            all_jobs = list(jm._jobs.values())
        counts: dict[str, int] = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
        for j in all_jobs:
            counts[j.status] = counts.get(j.status, 0) + 1
        return HealthResponse(status="ok", jobs=counts)

    # ── Jobs ──────────────────────────────────────────────────────────────────

    @app.post("/jobs", response_model=JobResponse, status_code=202, tags=["jobs"])
    def create_job(request: JobCreateRequest):
        jm: JobManager = app.state.job_manager
        job = jm.submit(request)
        return _make_job_response(job)

    @app.get("/jobs", response_model=list[JobResponse], tags=["jobs"])
    def list_jobs(
        status: Optional[str] = None,
        limit: int = 50,
    ):
        jm: JobManager = app.state.job_manager
        jobs = jm.list_jobs(status=status, limit=limit)
        return [_make_job_response(j) for j in jobs]

    @app.get("/jobs/{job_id}", response_model=JobResponse, tags=["jobs"])
    def get_job(job_id: str):
        jm: JobManager = app.state.job_manager
        job = jm.get(job_id)
        if job is None:
            raise HTTPException(404, detail=f"Job {job_id} not found")
        return _make_job_response(job)

    @app.delete("/jobs/{job_id}", tags=["jobs"])
    def cancel_job(job_id: str):
        jm: JobManager = app.state.job_manager
        job = jm.get(job_id)
        if job is None:
            raise HTTPException(404, detail=f"Job {job_id} not found")
        cancelled = jm.cancel(job_id)
        return {"cancelled": cancelled, "job_id": job_id}

    @app.post("/jobs/{job_id}/retry", response_model=JobResponse, status_code=202, tags=["jobs"])
    def retry_job(job_id: str, overrides: RetryRequest = RetryRequest()):
        jm: JobManager = app.state.job_manager
        try:
            new_job = jm.retry(job_id, overrides)
        except KeyError:
            raise HTTPException(404, detail=f"Job {job_id} not found")
        return _make_job_response(new_job)

    # ── Logs ──────────────────────────────────────────────────────────────────

    @app.get("/jobs/{job_id}/logs", tags=["logs"])
    async def get_logs(job_id: str, request: Request, cursor: int = 0):
        """
        Two modes based on Accept header:
        - Accept: text/event-stream  → SSE stream (real-time)
        - Default                    → JSON polling response
        """
        jm: JobManager = app.state.job_manager
        job = jm.get(job_id)
        if job is None:
            raise HTTPException(404, detail=f"Job {job_id} not found")

        accept = request.headers.get("accept", "")
        if "text/event-stream" in accept:
            return StreamingResponse(
                _sse_log_stream(jm, job_id, cursor),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Polling mode
        lines = jm.get_log_lines(job_id, cursor=cursor)
        new_cursor = cursor + len(lines)
        is_done = job.status in ("completed", "failed")
        return LogsResponse(job_id=job_id, lines=lines, cursor=new_cursor, is_done=is_done)

    # ── Files ─────────────────────────────────────────────────────────────────

    @app.get("/jobs/{job_id}/files", response_model=FileListResponse, tags=["files"])
    def list_files(job_id: str):
        jm: JobManager = app.state.job_manager
        job = jm.get(job_id)
        if job is None:
            raise HTTPException(404, detail=f"Job {job_id} not found")
        output_dir_str = str(job.output_dir) if job.output_dir else None
        return FileListResponse(
            job_id=job_id,
            output_dir=output_dir_str,
            files=jm.list_output_files(job_id),
        )

    @app.get("/jobs/{job_id}/files/{filename}", tags=["files"])
    def download_file(job_id: str, filename: str):
        if filename not in OUTPUT_FILES:
            raise HTTPException(404, detail=f"Unknown file: {filename}")
        jm: JobManager = app.state.job_manager
        job = jm.get(job_id)
        if job is None:
            raise HTTPException(404, detail=f"Job {job_id} not found")
        if job.output_dir is None:
            raise HTTPException(404, detail="Output directory not yet available")
        path = job.output_dir / filename
        if not path.exists():
            raise HTTPException(404, detail=f"{filename} not yet available")
        return FileResponse(str(path), filename=filename)

    # ── Flows ─────────────────────────────────────────────────────────────────

    @app.post("/flows", response_model=FlowResponse, status_code=201, tags=["flows"])
    def create_flow(body: FlowCreateRequest):
        fs: FlowStore = app.state.flow_store
        sched: FlowScheduler = app.state.scheduler
        if body.schedule:
            try:
                from apscheduler.triggers.cron import CronTrigger
                CronTrigger.from_crontab(body.schedule)
            except Exception as exc:
                raise HTTPException(422, detail=f"Invalid cron expression: {exc}")
        flow = fs.create(
            name=body.name,
            definition=body.definition.model_dump(),
            schedule=body.schedule,
            enabled=body.enabled,
        )
        sched.sync_flow(flow)
        return _make_flow_response(flow)

    @app.get("/flows", response_model=list[FlowResponse], tags=["flows"])
    def list_flows():
        fs: FlowStore = app.state.flow_store
        return [_make_flow_response(f) for f in fs.list()]

    @app.get("/flows/{flow_id}", response_model=FlowResponse, tags=["flows"])
    def get_flow(flow_id: str):
        fs: FlowStore = app.state.flow_store
        flow = fs.get(flow_id)
        if flow is None:
            raise HTTPException(404, detail=f"Flow {flow_id} not found")
        return _make_flow_response(flow)

    @app.patch("/flows/{flow_id}", response_model=FlowResponse, tags=["flows"])
    def update_flow(flow_id: str, body: FlowUpdateRequest):
        fs: FlowStore = app.state.flow_store
        sched: FlowScheduler = app.state.scheduler
        if fs.get(flow_id) is None:
            raise HTTPException(404, detail=f"Flow {flow_id} not found")
        # Use model_fields_set so explicit `null` values (e.g. clearing schedule) are applied
        raw = body.model_dump()
        updates: dict = {k: raw[k] for k in body.model_fields_set}
        if "definition" in updates and updates["definition"] is not None:
            updates["definition"] = body.definition.model_dump()  # type: ignore[union-attr]
        if updates.get("schedule") is not None:
            try:
                from apscheduler.triggers.cron import CronTrigger
                CronTrigger.from_crontab(updates["schedule"])
            except Exception as exc:
                raise HTTPException(422, detail=f"Invalid cron expression: {exc}")
        flow = fs.update(flow_id, **updates)
        sched.sync_flow(flow)
        return _make_flow_response(flow)

    @app.delete("/flows/{flow_id}", tags=["flows"])
    def delete_flow(flow_id: str):
        fs: FlowStore = app.state.flow_store
        sched: FlowScheduler = app.state.scheduler
        if not fs.delete(flow_id):
            raise HTTPException(404, detail=f"Flow {flow_id} not found")
        sched.remove_flow(flow_id)
        return {"deleted": True, "flow_id": flow_id}

    @app.post("/flows/{flow_id}/run", response_model=JobResponse, status_code=202, tags=["flows"])
    def run_flow(flow_id: str):
        fs: FlowStore = app.state.flow_store
        jm: JobManager = app.state.job_manager
        flow = fs.get(flow_id)
        if flow is None:
            raise HTTPException(404, detail=f"Flow {flow_id} not found")
        request = JobCreateRequest(**flow["definition"])
        job = jm.submit(request)
        return _make_job_response(job)

    return app


# ── SSE helper ────────────────────────────────────────────────────────────────

async def _sse_log_stream(jm: JobManager, job_id: str, start_cursor: int):
    cursor = start_cursor
    while True:
        lines = jm.get_log_lines(job_id, cursor=cursor)
        for line in lines:
            yield f"data: {json.dumps({'line': line})}\n\n"
        cursor += len(lines)

        job = jm.get(job_id)
        if job and job.status in ("completed", "failed"):
            yield f"data: {json.dumps({'done': True, 'status': job.status})}\n\n"
            break
        await asyncio.sleep(0.5)


# ── Module-level app instance (for uvicorn) ───────────────────────────────────

app = create_app()
