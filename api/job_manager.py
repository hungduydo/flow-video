from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Literal, Optional

from .models import FileInfo, JobCreateRequest, RetryRequest

# Whitelisted output files clients can list/download
OUTPUT_FILES = [
    "final_youtube.mp4",
    "final_tiktok.mp4",
    "final.mp4",
    "banner_youtube.jpg",
    "banner_tiktok.jpg",
    "captions_cn.srt",
    "captions_vn.srt",
    "metadata.json",
]


@dataclass
class Job:
    job_id: str
    request: JobCreateRequest
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    video_id: Optional[str] = None
    current_step: Optional[int | str] = None
    current_step_name: Optional[str] = None
    failed_step: Optional[int | str] = None
    failed_step_name: Optional[str] = None
    output_dir: Optional[Path] = None
    log_buffer: list[str] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None

    def output_files(self) -> list[str]:
        """Return list of output filenames that currently exist on disk."""
        if self.output_dir is None:
            return []
        return [f for f in OUTPUT_FILES if (self.output_dir / f).exists()]

    def file_list(self) -> list[FileInfo]:
        """Return FileInfo for all whitelisted files (available or not)."""
        result = []
        for name in OUTPUT_FILES:
            if self.output_dir is None:
                result.append(FileInfo(name=name, size_bytes=None, available=False))
                continue
            path = self.output_dir / name
            if path.exists():
                result.append(FileInfo(name=name, size_bytes=path.stat().st_size, available=True))
            else:
                result.append(FileInfo(name=name, size_bytes=None, available=False))
        return result


class JobManager:
    def __init__(self, max_workers: int = 2) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._runner: Optional[Callable[[Job], None]] = None

    def set_runner(self, runner: Callable[[Job], None]) -> None:
        """Set the pipeline runner function (avoids circular import at init time)."""
        self._runner = runner

    def submit(self, request: JobCreateRequest) -> Job:
        job = Job(job_id=str(uuid.uuid4()), request=request)
        with self._lock:
            self._jobs[job.job_id] = job
        assert self._runner is not None, "Runner not set — call set_runner() first"
        self._executor.submit(self._runner, job)
        return job

    def retry(self, job_id: str, overrides: RetryRequest) -> Job:
        """Clone a job with optional overrides and resubmit."""
        original = self.get(job_id)
        if original is None:
            raise KeyError(job_id)

        # Merge: start from original request, apply non-None overrides
        base = original.request.model_dump()
        for field_name, value in overrides.model_dump(exclude_none=True).items():
            base[field_name] = value

        # Auto-set from_step to failed_step if not explicitly overridden
        if overrides.from_step is None and original.failed_step is not None:
            fs = original.failed_step
            # Convert sub-steps ("1b", "1c", "2b") to their parent step number
            if isinstance(fs, str):
                parent = int(fs[0])
                base["from_step"] = parent
            else:
                base["from_step"] = fs

        new_request = JobCreateRequest(**base)
        return self.submit(new_request)

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None, limit: int = 50) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        # Most recent first
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None:
            return False
        job.cancel_event.set()
        return True

    def get_log_lines(self, job_id: str, cursor: int = 0) -> list[str]:
        job = self.get(job_id)
        if job is None:
            return []
        # list slice is GIL-atomic in CPython — no lock needed
        return job.log_buffer[cursor:]

    def list_output_files(self, job_id: str) -> list[FileInfo]:
        job = self.get(job_id)
        if job is None:
            return []
        return job.file_list()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
