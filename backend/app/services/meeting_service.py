from pathlib import Path
from datetime import datetime
from ..repositories.meeting_repository import MeetingRepository
from ..gpu_client import TranscriptionService
from .job_store import JobStore

class MeetingService:
    """Service handling meeting business logic."""

    def __init__(
        self,
        repo: MeetingRepository,
        transcriber: TranscriptionService,
        job_store: JobStore,
    ):
        self.repo = repo
        self.transcriber = transcriber
        self.job_store = job_store

    async def create_meeting(
        self,
        title: str,
        date: datetime,
        platform: str | None = None,
        url: str | None = None,
        duration: float | None = None,
    ) -> int:
        return await self.repo.create(title, date, platform, url, duration)

    async def process_upload(
        self,
        job_id: str,
        meeting_id: int,
        mic_path: Path,
        tab_path: Path,
        metadata: dict,
    ):
        """Background task to process uploaded meeting files."""
        self.job_store.update_status(job_id, "processing")

        try:
            result = await self.transcriber.transcribe(
                mic_path=mic_path,
                tab_path=tab_path,
                metadata=metadata,
                job_id=job_id,
            )

            if result.success:
                await self.repo.save_transcript(
                    meeting_id=meeting_id,
                    segments=result.segments or [],
                    formatted=result.formatted or "",
                    stats=result.stats or {},
                )
                self.job_store.update_status(
                    job_id, 
                    "completed",
                    result={
                        "meeting_id": meeting_id,
                        "segments_count": len(result.segments or []),
                        "used_fallback": result.used_fallback,
                    }
                )
            else:
                await self.repo.update_status(meeting_id, "failed")
                self.job_store.update_status(job_id, "failed", error=result.error)

        except Exception as e:
            await self.repo.update_status(meeting_id, "failed")
            self.job_store.update_status(job_id, "failed", error=str(e))

    async def get_meeting_details(self, meeting_id: int) -> dict | None:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            return None
        
        transcript = await self.repo.get_transcript(meeting_id)
        return {
            "meeting": meeting,
            "transcript": transcript,
        }

    async def list_meetings(self, limit: int = 50, offset: int = 0) -> dict:
        meetings = await self.repo.list(limit, offset)
        return {"meetings": meetings, "count": len(meetings)}
