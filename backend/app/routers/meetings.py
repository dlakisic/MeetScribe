from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..config import Config
from ..dependencies import get_config, get_meeting_service, require_auth
from ..schemas.meeting import MeetingUpdate, SpeakerUpdate
from ..services.meeting_service import MeetingService

router = APIRouter(prefix="/api/meetings", dependencies=[Depends(require_auth)])


@router.patch("/{meeting_id}")
async def update_meeting(
    meeting_id: int,
    body: MeetingUpdate,
    service: MeetingService = Depends(get_meeting_service),
):
    """Update meeting fields (title, etc.)."""
    updated = await service.update_meeting(meeting_id, body.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


@router.patch("/{meeting_id}/speakers")
async def update_speaker(
    meeting_id: int,
    body: SpeakerUpdate,
    service: MeetingService = Depends(get_meeting_service),
):
    """Rename a speaker globally for a meeting."""
    count = await service.update_speaker(meeting_id, body.old_name, body.new_name)
    return {"updated_count": count}


@router.delete("/{meeting_id}")
async def delete_meeting(
    meeting_id: int,
    service: MeetingService = Depends(get_meeting_service),
):
    """Delete a meeting and all related data."""
    deleted = await service.delete_meeting(meeting_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"ok": True}


@router.get("/{meeting_id}/audio")
async def get_meeting_audio(
    meeting_id: int,
    service: MeetingService = Depends(get_meeting_service),
    config: Config = Depends(get_config),
):
    """Stream the audio file for a meeting."""
    meeting = await service.repo.get(meeting_id)
    if not meeting or not meeting.get("audio_file"):
        raise HTTPException(status_code=404, detail="Audio not found")

    # Construct absolute path from relative path in DB
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
