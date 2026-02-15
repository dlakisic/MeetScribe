"""MeetScribe Backend API."""

import json
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import Config, load_config
from .core.auth import security, verify_token
from .core.logging import get_logger
from .database import Database
from .gpu_client import TranscriptionService
from .repositories.meeting_repository import MeetingRepository
from .services.extraction_service import ExtractionService
from .services.job_store import JobStore
from .services.meeting_service import MeetingService

log = get_logger("api")

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
    extraction_service = ExtractionService()

    meeting_service = MeetingService(repo, transcriber, job_store, extraction_service)

    log.info("Backend started")
    log.info(f"Data dir: {config.data_dir}")
    log.info(f"GPU worker: {config.gpu.ssh_user}@{config.gpu.host}")
    log.info(f"Fallback enabled: {config.fallback.enabled}")

    yield

    await db.close()


app = FastAPI(
    title="MeetScribe API",
    description="Self-hosted meeting transcription backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth dependency that uses global config
def require_auth(credentials=Depends(security)):
    """Dependency to require authentication on protected endpoints."""
    verify_token(credentials, config.api_token)


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


@app.post("/api/upload", dependencies=[Depends(require_auth)])
async def upload_meeting(
    background_tasks: BackgroundTasks,
    mic_file: UploadFile | None = File(None, description="Microphone audio file"),
    tab_file: UploadFile | None = File(None, description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
):
    """Upload meeting audio files for transcription. At least one file required."""
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")

    if not mic_file and not tab_file:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]
    job_dir = config.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    mic_path = None
    tab_path = None

    if mic_file:
        mic_path = job_dir / f"mic_{mic_file.filename}"
        with open(mic_path, "wb") as f:
            shutil.copyfileobj(mic_file.file, f)

    if tab_file:
        tab_path = job_dir / f"tab_{tab_file.filename}"
        with open(tab_path, "wb") as f:
            shutil.copyfileobj(tab_file.file, f)

    # Determine primary audio file (tab preferred, contains all participants)
    primary_audio = tab_path or mic_path
    audio_file = str(primary_audio.relative_to(config.upload_dir)) if primary_audio else None

    # Create meeting record
    meeting_id = await meeting_service.repo.create(
        title=meta.get("title", "Untitled Meeting"),
        date=datetime.fromisoformat(meta.get("date", datetime.now().isoformat())),
        platform=meta.get("platform"),
        url=meta.get("url"),
        duration=meta.get("duration"),
        audio_file=audio_file,
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


@app.get("/api/status/{job_id}", dependencies=[Depends(require_auth)])
async def get_job_status(job_id: str):
    """Get the status of a transcription job."""
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/transcripts", dependencies=[Depends(require_auth)])
async def list_transcripts(limit: int = 50, offset: int = 0):
    """List all meetings with their transcription status."""
    return await meeting_service.list_meetings(limit, offset)


@app.get("/api/transcripts/{meeting_id}", dependencies=[Depends(require_auth)])
async def get_transcript(meeting_id: int):
    """Get the full transcript for a meeting."""
    result = await meeting_service.get_meeting_details(meeting_id)
    if not result:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return result


class SegmentUpdate(BaseModel):
    text: str


@app.patch("/api/segments/{segment_id}", dependencies=[Depends(require_auth)])
async def update_segment(segment_id: int, body: SegmentUpdate):
    """Update a segment's text."""
    updated = await meeting_service.update_segment_text(segment_id, body.text)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"ok": True}


class MeetingUpdate(BaseModel):
    title: str | None = None


@app.patch("/api/meetings/{meeting_id}", dependencies=[Depends(require_auth)])
async def update_meeting(meeting_id: int, body: MeetingUpdate):
    """Update meeting fields (title, etc.)."""
    updated = await meeting_service.update_meeting(meeting_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


class SpeakerUpdate(BaseModel):
    old_name: str
    new_name: str


@app.patch("/api/meetings/{meeting_id}/speakers", dependencies=[Depends(require_auth)])
async def update_speaker(meeting_id: int, body: SpeakerUpdate):
    """Rename a speaker globally for a meeting."""
    count = await meeting_service.update_speaker(meeting_id, body.old_name, body.new_name)
    return {"updated_count": count}


@app.delete("/api/meetings/{meeting_id}", dependencies=[Depends(require_auth)])
async def delete_meeting(meeting_id: int):
    """Delete a meeting and all related data."""
    deleted = await meeting_service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


@app.get("/api/meetings/{meeting_id}/audio", dependencies=[Depends(require_auth)])
async def get_meeting_audio(meeting_id: int):
    """Stream the audio file for a meeting."""
    meeting = await meeting_service.repo.get(meeting_id)
    if not meeting or not meeting.get("audio_file"):
        raise HTTPException(status_code=404, detail="Audio not found")

    audio_path = config.upload_dir / meeting["audio_file"]
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file missing")

    # Guess media type from extension
    suffix = audio_path.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
        ".mp4": "video/mp4",
        ".flac": "audio/flac",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(audio_path, media_type=media_type, filename=audio_path.name)


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
