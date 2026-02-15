from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_meeting_service, require_auth
from ..schemas.meeting import SegmentUpdate
from ..services.meeting_service import MeetingService

router = APIRouter(prefix="/api/segments", dependencies=[Depends(require_auth)])


@router.patch("/{segment_id}")
async def update_segment(
    segment_id: int,
    body: SegmentUpdate,
    service: MeetingService = Depends(get_meeting_service),
):
    """Update a segment's text."""
    updated = await service.update_segment_text(segment_id, body.text)
    if not updated:
        raise HTTPException(status_code=404, detail="Segment not found")
    return {"ok": True}
