import asyncio
import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from ..config import Config
from ..core.logging import get_logger
from ..dependencies import get_config, get_job_store, get_meeting_service, require_auth
from ..services.job_store import JobStore
from ..services.meeting_service import MeetingService

router = APIRouter(prefix="/api/upload", dependencies=[Depends(require_auth)])
log = get_logger("upload")


def _safe_filename(name: str) -> str:
    """Sanitize uploaded filename to prevent path traversal."""
    safe = Path(name).name
    safe = safe.replace("\0", "").replace("/", "_").replace("\\", "_")
    safe = safe.replace("..", "")
    return safe or "unnamed"


def _parse_date(date_str: str | None) -> datetime:
    """Parse ISO date string, returning now() if missing or invalid."""
    if not date_str:
        return datetime.now()
    try:
        return datetime.fromisoformat(date_str)
    except ValueError, TypeError:
        raise HTTPException(status_code=400, detail="Invalid date format")


def _parse_metadata(metadata_str: str) -> dict:
    """Parse and validate metadata JSON."""
    try:
        return json.loads(metadata_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid metadata JSON")


_CHUNK_SIZE = 1024 * 1024


def _save_file(upload_file: UploadFile, dest_path: Path, max_bytes: int):
    """Save uploaded file to destination, rejecting files over max_bytes."""
    written = 0
    with open(dest_path, "wb") as f:
        while chunk := upload_file.file.read(_CHUNK_SIZE):
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large (max {max_bytes // (1024 * 1024)} MB)",
                )
            f.write(chunk)


@router.post("")
async def upload_meeting(
    background_tasks: BackgroundTasks,
    request: Request,
    mic_file: UploadFile | None = File(None, description="Microphone audio file"),
    tab_file: UploadFile | None = File(None, description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
    config: Config = Depends(get_config),
    service: MeetingService = Depends(get_meeting_service),
    job_store: JobStore = Depends(get_job_store),
):
    """Upload meeting audio files for transcription. At least one file required."""
    meta = _parse_metadata(metadata)
    request_id = getattr(request.state, "request_id", None)

    if not mic_file and not tab_file:
        raise HTTPException(status_code=400, detail="At least one audio file is required")
    # Validate before writing anything to disk so a bad request leaves no files.
    meeting_date = _parse_date(meta.get("date"))

    job_id = str(uuid.uuid4())[:8]
    job_dir = config.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    mic_path = None
    tab_path = None
    max_bytes = config.max_upload_mb * 1024 * 1024

    try:
        if mic_file:
            mic_path = job_dir / f"mic_{_safe_filename(mic_file.filename)}"
            await asyncio.to_thread(_save_file, mic_file, mic_path, max_bytes)

        if tab_file:
            tab_path = job_dir / f"tab_{_safe_filename(tab_file.filename)}"
            await asyncio.to_thread(_save_file, tab_file, tab_path, max_bytes)
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    primary_audio = tab_path or mic_path
    audio_file = str(primary_audio.relative_to(config.upload_dir)) if primary_audio else None

    meeting_id = await service.create_meeting(
        title=meta.get("title", "Untitled Meeting"),
        date=meeting_date,
        platform=meta.get("platform"),
        url=meta.get("url"),
        duration=meta.get("duration"),
        audio_file=audio_file,
    )

    meta["local_speaker"] = config.local_speaker_name
    meta["remote_speaker"] = "Interlocuteur"
    if request_id:
        meta["request_id"] = request_id

    await job_store.create_job(job_id, meeting_id)
    log.info(
        "Upload accepted",
        extra={
            "request_id": request_id,
            "job_id": job_id,
            "meeting_id": meeting_id,
            "has_mic": bool(mic_file),
            "has_tab": bool(tab_file),
        },
    )

    background_tasks.add_task(
        service.process_upload,
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
