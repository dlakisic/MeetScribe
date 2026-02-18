"""
GPU Worker HTTP Server
Receives audio files via HTTP and returns transcripts
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from core.logging import get_logger
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from transcribe import Transcriber, process_meeting

log = get_logger("server")

app = FastAPI(title="MeetScribe GPU Worker", version="0.1.0")

WORKER_TOKEN = os.environ.get("MEETSCRIBE_GPU_WORKER_TOKEN", "")


# ---------------------------------------------------------------------------
# Job store (in-memory)
# ---------------------------------------------------------------------------


class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkerJob:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress_step: str = ""
    progress_detail: str = ""
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class WorkerJobStore:
    """In-memory job tracker. Keeps current job + last N completed."""

    def __init__(self, history_size: int = 10):
        self._jobs: dict[str, WorkerJob] = {}
        self._history_size = history_size

    def create(self, job_id: str) -> WorkerJob:
        job = WorkerJob(job_id=job_id)
        self._jobs[job_id] = job
        self._trim()
        return job

    def get(self, job_id: str) -> WorkerJob | None:
        return self._jobs.get(job_id)

    def _trim(self):
        finished = [
            j for j in self._jobs.values() if j.status in (JobStatus.COMPLETED, JobStatus.FAILED)
        ]
        if len(finished) > self._history_size:
            finished.sort(key=lambda j: j.completed_at or 0)
            for j in finished[: -self._history_size]:
                del self._jobs[j.job_id]


job_store = WorkerJobStore()


# ---------------------------------------------------------------------------
# Middleware & helpers
# ---------------------------------------------------------------------------


@app.middleware("http")
async def verify_worker_token(request: Request, call_next):
    """Reject requests with invalid X-Worker-Token when a token is configured."""
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    request.state.request_id = request_id
    if WORKER_TOKEN:
        token = request.headers.get("X-Worker-Token", "")
        if token != WORKER_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
                headers={"X-Request-ID": request_id},
            )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _safe_filename(raw: str | None) -> str:
    """Sanitize an uploaded filename to prevent path traversal."""
    if not raw:
        return "upload"
    name = Path(raw).name  # strip directory components
    name = re.sub(r"[^\w.\-]", "_", name)  # keep only safe chars
    return name or "upload"


# ---------------------------------------------------------------------------
# Worker state
# ---------------------------------------------------------------------------


@dataclass
class WorkerState:
    """Encapsulated worker configuration and runtime state."""

    model_size: str = "large-v3"
    device: str = "cuda"
    language: str | None = None
    transcriber: Transcriber | None = None
    lock: asyncio.Lock | None = None
    current_job_id: str | None = None
    current_job_start: float | None = None

    def get_transcriber(self) -> Transcriber:
        """Get or create the transcriber instance (lazy singleton)."""
        if self.transcriber is None:
            log.info(f"Loading Whisper model '{self.model_size}' on {self.device}")
            self.transcriber = Transcriber(
                model_size=self.model_size, device=self.device, language=self.language
            )
            log.info("Model loaded")
        return self.transcriber


worker = WorkerState()


@app.on_event("startup")
async def startup():
    """Preload model on startup and initialize lock."""
    worker.lock = asyncio.Lock()

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, worker.get_transcriber)


# ---------------------------------------------------------------------------
# Background transcription task
# ---------------------------------------------------------------------------


async def _run_transcription(
    job_id: str,
    job_dir: Path,
    mic_path: Path | None,
    tab_path: Path | None,
    meta: dict,
    request_id: str | None,
):
    """Background task: acquire lock, run pipeline, update job store."""
    job = job_store.get(job_id)
    if not job:
        return

    if worker.lock.locked():
        log.info(
            f"[{job_id}] Worker is busy, queueing request",
            extra={"request_id": request_id, "job_id": job_id},
        )

    async with worker.lock:
        worker.current_job_id = job_id
        worker.current_job_start = time.monotonic()
        job.status = JobStatus.PROCESSING
        job.started_at = time.monotonic()

        log.info(
            f"[{job_id}] Acquired lock, starting transcription",
            extra={"request_id": request_id, "job_id": job_id},
        )

        def on_progress(step: str, detail: str):
            """Thread-safe callback: updates job state from executor thread."""
            job.progress_step = step
            job.progress_detail = detail
            log.info(
                f"[{job_id}] {detail}",
                extra={"request_id": request_id, "job_id": job_id, "step": step},
            )

        try:
            output_path = job_dir / "output.json"
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: process_meeting(
                    mic_path=mic_path,
                    tab_path=tab_path,
                    metadata=meta,
                    output_path=output_path,
                    transcriber=worker.get_transcriber(),
                    on_progress=on_progress,
                ),
            )

            elapsed = round(time.monotonic() - job.started_at, 1)
            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = time.monotonic()
            log.info(
                f"[{job_id}] Transcription complete in {elapsed}s",
                extra={"request_id": request_id, "job_id": job_id, "duration_seconds": elapsed},
            )

        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = time.monotonic()
            log.error(
                f"[{job_id}] Transcription failed: {e}",
                extra={"request_id": request_id, "job_id": job_id},
            )

        finally:
            worker.current_job_id = None
            worker.current_job_start = None
            shutil.rmtree(job_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check endpoint."""
    result = {
        "status": "ok",
        "model": worker.model_size,
        "device": worker.device,
        "model_loaded": worker.transcriber is not None,
        "locked": worker.lock.locked() if worker.lock else False,
    }
    if worker.current_job_id:
        result["current_job"] = {
            "job_id": worker.current_job_id,
            "elapsed_seconds": round(time.monotonic() - worker.current_job_start, 1),
        }
    return result


@app.post("/transcribe", status_code=202)
async def transcribe(
    request: Request,
    mic_file: UploadFile | None = File(None, description="Microphone audio file"),
    tab_file: UploadFile | None = File(None, description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
):
    """Accept audio files for transcription. Returns immediately with a job ID."""
    if not worker.lock:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    if not mic_file and not tab_file:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    job_id = meta.get("job_id", uuid4().hex[:12])
    request_id = meta.get("request_id") or getattr(request.state, "request_id", None)
    if request_id:
        meta["request_id"] = request_id

    # Save uploaded files to temp dir (fast I/O, not the bottleneck)
    job_dir = Path(tempfile.mkdtemp(prefix=f"meetscribe_{job_id}_"))

    mic_path = None
    tab_path = None

    if mic_file:
        mic_path = job_dir / f"mic_{_safe_filename(mic_file.filename)}"
        with open(mic_path, "wb") as f:
            shutil.copyfileobj(mic_file.file, f)

    if tab_file:
        tab_path = job_dir / f"tab_{_safe_filename(tab_file.filename)}"
        with open(tab_path, "wb") as f:
            shutil.copyfileobj(tab_file.file, f)

    # Create job and spawn background task
    job_store.create(job_id)
    asyncio.create_task(_run_transcription(job_id, job_dir, mic_path, tab_path, meta, request_id))

    log.info(
        f"[{job_id}] Job accepted, processing in background",
        extra={"request_id": request_id, "job_id": job_id},
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get the status and result of a transcription job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response: dict[str, Any] = {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress_step": job.progress_step,
        "progress_detail": job.progress_detail,
    }

    if job.started_at and not job.completed_at:
        response["elapsed_seconds"] = round(time.monotonic() - job.started_at, 1)

    if job.status == JobStatus.COMPLETED:
        response["result"] = job.result
    elif job.status == JobStatus.FAILED:
        response["error"] = job.error

    return response


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GPU Worker HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind to")
    parser.add_argument("--model", default="large-v3", help="Whisper model size")
    parser.add_argument("--device", default="cuda", help="Device (cuda/cpu)")
    parser.add_argument(
        "--language", default=None, help="Language code (e.g. fr, en). Auto-detect if omitted."
    )

    args = parser.parse_args()

    worker.model_size = args.model
    worker.device = args.device
    worker.language = args.language

    log.info(f"Starting GPU Worker on {args.host}:{args.port}")
    log.info(
        f"Model: {worker.model_size}, Device: {worker.device}, Language: {worker.language or 'auto-detect'}"
    )

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
