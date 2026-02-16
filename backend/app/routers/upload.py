import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from ..config import Config
from ..dependencies import get_config, get_job_store, get_meeting_service, require_auth
from ..services.job_store import JobStore
from ..services.meeting_service import MeetingService

router = APIRouter(prefix="/api/upload", dependencies=[Depends(require_auth)])


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


def _save_file(upload_file: UploadFile, dest_path: Path):
    """Save uploaded file to destination."""
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(upload_file.file, f)


@router.post("")
async def upload_meeting(
    background_tasks: BackgroundTasks,
    mic_file: UploadFile | None = File(None, description="Microphone audio file"),
    tab_file: UploadFile | None = File(None, description="Tab audio file"),
    metadata: str = Form(..., description="Meeting metadata as JSON"),
    config: Config = Depends(get_config),
    service: MeetingService = Depends(get_meeting_service),
    job_store: JobStore = Depends(get_job_store),
):
    """Upload meeting audio files for transcription. At least one file required."""
    meta = _parse_metadata(metadata)

    if not mic_file and not tab_file:
        raise HTTPException(status_code=400, detail="At least one audio file is required")

    job_id = str(uuid.uuid4())[:8]
    job_dir = config.upload_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    mic_path = None
    tab_path = None

    if mic_file:
        mic_path = job_dir / f"mic_{_safe_filename(mic_file.filename)}"
        _save_file(mic_file, mic_path)

    if tab_file:
        tab_path = job_dir / f"tab_{_safe_filename(tab_file.filename)}"
        _save_file(tab_file, tab_path)

    primary_audio = tab_path or mic_path
    audio_file = str(primary_audio.relative_to(config.upload_dir)) if primary_audio else None

    meeting_id = await service.create_meeting(
        title=meta.get("title", "Untitled Meeting"),
        date=_parse_date(meta.get("date")),
        platform=meta.get("platform"),
        url=meta.get("url"),
        duration=meta.get("duration"),
        audio_file=audio_file,
    )

    meta["local_speaker"] = config.local_speaker_name
    meta["remote_speaker"] = "Interlocuteur"

    await job_store.create_job(job_id, meeting_id)

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
