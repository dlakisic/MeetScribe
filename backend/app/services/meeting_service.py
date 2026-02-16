from datetime import datetime
from pathlib import Path

from ..core.logging import get_logger
from ..interfaces import (
    AbstractExtractionService,
    AbstractJobStore,
    AbstractMeetingRepository,
    AbstractTranscriber,
)

log = get_logger("service")


class MeetingService:
    """Service handling meeting business logic."""

    def __init__(
        self,
        repo: AbstractMeetingRepository,
        transcriber: AbstractTranscriber,
        job_store: AbstractJobStore,
        extraction_service: AbstractExtractionService,
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
        audio_file: str | None = None,
    ) -> int:
        return await self.repo.create(title, date, platform, url, duration, audio_file)

    async def process_upload(
        self,
        job_id: str,
        meeting_id: int,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
    ):
        """Background task to process uploaded meeting files."""
        await self.job_store.update_status(job_id, "processing")
        metadata["job_id"] = job_id

        try:
            result = await self.transcriber.transcribe(
                mic_path=mic_path,
                tab_path=tab_path,
                metadata=metadata,
                job_id=job_id,
            )

            if not result.success:
                await self._mark_failed(job_id, meeting_id, result.error)
                return

            await self.repo.save_transcript(
                meeting_id=meeting_id,
                segments=result.segments or [],
                formatted=result.formatted or "",
                stats=result.stats or {},
            )
            await self._run_extraction(meeting_id, result.formatted or "")

            await self.job_store.update_status(
                job_id,
                "completed",
                result={
                    "meeting_id": meeting_id,
                    "segments_count": len(result.segments or []),
                    "used_fallback": result.used_fallback,
                },
            )

        except Exception as e:
            await self._mark_failed(job_id, meeting_id, str(e))

    async def _run_extraction(self, meeting_id: int, formatted_text: str):
        """Extract structured data (summary, actions, decisions) from transcript."""
        try:
            log.info(f"Starting extraction for meeting {meeting_id}")
            extracted = await self.extraction_service.extract_from_transcript(formatted_text)
            await self.repo.save_extracted_data(meeting_id, extracted.model_dump())
            log.info(f"Extraction completed for meeting {meeting_id}")
        except Exception as e:
            log.warning(f"Extraction failed for meeting {meeting_id}: {e}")

    async def _mark_failed(self, job_id: str, meeting_id: int, error: str | None):
        """Mark both job and meeting as failed."""
        await self.repo.update_status(meeting_id, "failed")
        await self.job_store.update_status(job_id, "failed", error=error)

    async def get_meeting(self, meeting_id: int) -> dict | None:
        return await self.repo.get(meeting_id)

    async def get_meeting_details(self, meeting_id: int) -> dict | None:
        meeting = await self.repo.get(meeting_id)
        if not meeting:
            return None

        transcript = await self.repo.get_transcript(meeting_id)
        return {
            "meeting": meeting,
            "transcript": transcript,
        }

    async def update_meeting(self, meeting_id: int, fields: dict) -> bool:
        return await self.repo.update_fields(meeting_id, fields)

    async def update_segment_text(self, segment_id: int, text: str) -> bool:
        return await self.repo.update_segment_text(segment_id, text)

    async def update_speaker(self, meeting_id: int, old_name: str, new_name: str) -> int:
        return await self.repo.update_speaker(meeting_id, old_name, new_name)

    async def delete_meeting(self, meeting_id: int) -> bool:
        return await self.repo.delete(meeting_id)

    async def list_meetings(self, limit: int = 50, offset: int = 0) -> dict:
        meetings = await self.repo.list(limit, offset)
        return {"meetings": meetings, "count": len(meetings)}

    async def is_gpu_available(self) -> bool:
        """Check GPU availability via the transcriber interface."""
        return await self.transcriber.is_gpu_available()
