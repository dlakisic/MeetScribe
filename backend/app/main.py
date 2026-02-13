"""MeetScribe Backend API."""

import asyncio
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from .config import load_config, Config
from .database import Database
from .gpu_client import TranscriptionService
from .repositories.meeting_repository import MeetingRepository
from .services.job_store import JobStore
from .services.meeting_service import MeetingService


# Global instances
config: Config
db: Database
meeting_service: MeetingService
job_store: JobStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - setup and teardown."""
    global config, db, meeting_service, job_store

    config = load_config()
    db = Database(config.db_path)
    await db.connect()
    
    # Initialize infrastructure and services
    repo = MeetingRepository(db)
    transcriber = TranscriptionService(config)
    job_store = JobStore()
    
    meeting_service = MeetingService(repo, transcriber, job_store)

    print(f"MeetScribe Backend started")
    print(f"  Data dir: {config.data_dir}")
    print(f"  GPU worker: {config.gpu.ssh_user}@{config.gpu.host}")
    print(f"  Fallback enabled: {config.fallback.enabled}")

    yield

    await db.close()


app = FastAPI(
    title="MeetScribe API",
    description="Self-hosted meeting transcription backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "MeetScribe", "version": "0.1.0"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    gpu_available = await meeting_service.transcriber.gpu_client.is_gpu_available()
    return {
        "status": "ok",
        "gpu_available": gpu_available,
        "fallback_enabled": config.fallback.enabled,
    }


@app.post("/api/upload")
async def upload_meeting(
    background_tasks: BackgroundTasks,
    mic_file: UploadFile = File(..., description="Microphone audio file"),
    tab_file: UploadFile = File(..., description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
):
    """Upload meeting audio files for transcription."""
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]
    job_dir = config.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    mic_path = job_dir / f"mic_{mic_file.filename}"
    tab_path = job_dir / f"tab_{tab_file.filename}"

    with open(mic_path, "wb") as f:
        shutil.copyfileobj(mic_file.file, f)
    with open(tab_path, "wb") as f:
        shutil.copyfileobj(tab_file.file, f)

    # Create meeting record
    meeting_id = await meeting_service.repo.create(
        title=meta.get("title", "Untitled Meeting"),
        date=datetime.fromisoformat(meta.get("date", datetime.now().isoformat())),
        platform=meta.get("platform"),
        url=meta.get("url"),
        duration=meta.get("duration"),
    )

    # Add local speaker name to metadata
    meta["local_speaker"] = config.local_speaker_name
    meta["remote_speaker"] = "Interlocuteur"

    # Initialize job tracking
    job_store.create_job(job_id, meeting_id)

    # Start background processing via Service
    background_tasks.add_task(
        meeting_service.process_upload,
        job_id=job_id,
        meeting_id=meeting_id,
        mic_path=mic_path,
        tab_path=tab_path,
        metadata=meta,
    )

    return {
        "job_id": job_id,
        "meeting_id": meeting_id,
        "status": "queued",
    }


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a transcription job."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/transcripts")
async def list_transcripts(limit: int = 50, offset: int = 0):
    """List all meetings with their transcription status."""
    return await meeting_service.list_meetings(limit, offset)


@app.get("/api/transcripts/{meeting_id}")
async def get_transcript(meeting_id: int):
    """Get the full transcript for a meeting."""
    result = await meeting_service.get_meeting_details(meeting_id)
    if not result:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return result


# Simple CLI to run the server
def main():
    import uvicorn

    config = load_config()
    uvicorn.run(
        "backend.app.main:app",
        host=config.host,
        port=config.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
