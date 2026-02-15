from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_meeting_service, require_auth
from ..services.meeting_service import MeetingService

router = APIRouter(prefix="/api/transcripts", dependencies=[Depends(require_auth)])


@router.get("")
async def list_transcripts(
    limit: int = 50,
    offset: int = 0,
    service: MeetingService = Depends(get_meeting_service),
):
    """List all meetings with their transcription status."""
    return await service.list_meetings(limit, offset)


@router.get("/{meeting_id}")
async def get_transcript(
    meeting_id: int,
    service: MeetingService = Depends(get_meeting_service),
):
    """Get the full transcript for a meeting."""
    result = await service.get_meeting_details(meeting_id)
    if not result:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return result
