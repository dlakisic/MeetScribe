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
from pathlib import Path

import uvicorn
from core.logging import get_logger
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from transcribe import Transcriber, process_meeting

log = get_logger("server")

app = FastAPI(title="MeetScribe GPU Worker", version="0.1.0")

WORKER_TOKEN = os.environ.get("MEETSCRIBE_GPU_WORKER_TOKEN", "")


@app.middleware("http")
async def verify_worker_token(request: Request, call_next):
    """Reject requests with invalid X-Worker-Token when a token is configured."""
    if WORKER_TOKEN:
        token = request.headers.get("X-Worker-Token", "")
        if token != WORKER_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


def _safe_filename(raw: str | None) -> str:
    """Sanitize an uploaded filename to prevent path traversal."""
    if not raw:
        return "upload"
    name = Path(raw).name  # strip directory components
    name = re.sub(r"[^\w.\-]", "_", name)  # keep only safe chars
    return name or "upload"


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


@app.post("/transcribe")
async def transcribe(
    mic_file: UploadFile | None = File(None, description="Microphone audio file"),
    tab_file: UploadFile | None = File(None, description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
):
    """Transcribe uploaded audio files."""
    if not worker.lock:
        raise HTTPException(status_code=500, detail="Server not initialized")

    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    job_id = meta.get("job_id", "unknown")

    if worker.lock.locked():
        log.info(f"[{job_id}] Worker is busy, queueing request")

    async with worker.lock:
        worker.current_job_id = job_id
        worker.current_job_start = time.monotonic()
        log.info(f"[{job_id}] Acquired lock, starting transcription")

        job_dir = Path(tempfile.mkdtemp(prefix=f"meetscribe_{job_id}_"))

        try:
            if not mic_file and not tab_file:
                raise HTTPException(status_code=400, detail="At least one audio file is required")

            mic_path = None
            tab_path = None
            output_path = job_dir / "output.json"

            if mic_file:
                mic_path = job_dir / f"mic_{_safe_filename(mic_file.filename)}"
                with open(mic_path, "wb") as f:
                    shutil.copyfileobj(mic_file.file, f)

            if tab_file:
                tab_path = job_dir / f"tab_{_safe_filename(tab_file.filename)}"
                with open(tab_path, "wb") as f:
                    shutil.copyfileobj(tab_file.file, f)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: process_meeting(
                    mic_path=mic_path,
                    tab_path=tab_path,
                    metadata=meta,
                    output_path=output_path,
                    transcriber=worker.get_transcriber(),
                ),
            )

            elapsed = round(time.monotonic() - worker.current_job_start, 1)
            log.info(f"[{job_id}] Transcription complete in {elapsed}s")
            return JSONResponse(content=result)

        except HTTPException:
            raise
        except Exception as e:
            log.error(f"[{job_id}] Transcription failed: {e}")
            raise HTTPException(status_code=500, detail="Internal transcription error")

        finally:
            worker.current_job_id = None
            worker.current_job_start = None
            shutil.rmtree(job_dir, ignore_errors=True)


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
