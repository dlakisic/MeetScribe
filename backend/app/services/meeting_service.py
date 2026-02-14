from datetime import datetime
from pathlib import Path

from ..core.logging import get_logger
from ..gpu_client import TranscriptionService
from ..repositories.meeting_repository import MeetingRepository
from .extraction_service import ExtractionService
from .job_store import JobStore

log = get_logger("service")


class MeetingService:
    """Service handling meeting business logic."""

    def __init__(
        self,
        repo: MeetingRepository,
        transcriber: TranscriptionService,
        job_store: JobStore,
        extraction_service: ExtractionService,
    ):
        self.repo = repo
        self.transcriber = transcriber
        self.job_store = job_store
        self.extraction_service = extraction_service

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
        mic_path: Path | None,
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

                # Extract structured data (Actions, Summary)
                try:
                    log.info(f"Starting extraction for meeting {meeting_id}")
                    extracted = await self.extraction_service.extract_from_transcript(
                        result.formatted or ""
                    )
                    await self.repo.save_extracted_data(meeting_id, extracted.model_dump())
                    log.info(f"Extraction completed for meeting {meeting_id}")
                except Exception as e:
                    log.warning(f"Extraction failed for meeting {meeting_id}: {e}")

                self.job_store.update_status(
                    job_id,
                    "completed",
                    result={
                        "meeting_id": meeting_id,
                        "segments_count": len(result.segments or []),
                        "used_fallback": result.used_fallback,
                    },
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
