from datetime import datetime

from sqlmodel import desc, select

from ..database import Database
from ..interfaces import AbstractMeetingRepository
from ..models import Meeting, Segment, Transcript


class MeetingRepository(AbstractMeetingRepository):
    """Repository for accessing meeting data via SQLModel."""

    UPDATABLE_FIELDS = {"title", "platform", "url", "duration"}

    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        title: str,
        date: datetime,
        platform: str | None = None,
        url: str | None = None,
        duration: float | None = None,
        audio_file: str | None = None,
    ) -> int:
        """Create a new meeting record."""
        meeting = Meeting(
            title=title,
            date=date,
            platform=platform,
            url=url,
            duration=duration,
            audio_file=audio_file,
        )
        async with self.db.session() as session:
            session.add(meeting)
            await session.commit()
            await session.refresh(meeting)
            return meeting.id

    async def update_status(self, meeting_id: int, status: str):
        """Update meeting status."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            if meeting:
                meeting.status = status
                meeting.updated_at = datetime.now()
                session.add(meeting)
                await session.commit()

    async def update_fields(self, meeting_id: int, fields: dict) -> bool:
        """Update allowed meeting fields only."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            if not meeting:
                return False
            for key, value in fields.items():
                if key in self.UPDATABLE_FIELDS:
                    setattr(meeting, key, value)
            meeting.updated_at = datetime.now()
            session.add(meeting)
            await session.commit()
            return True

    async def save_transcript(
        self,
        meeting_id: int,
        segments: list[dict],
        formatted: str,
        stats: dict,
    ):
        """Save transcript and segments for a meeting."""
        async with self.db.session() as session:
            async with session.begin():
                statement = select(Transcript).where(Transcript.meeting_id == meeting_id)
                results = await session.exec(statement)
                transcript = results.first()

                if not transcript:
                    transcript = Transcript(
                        meeting_id=meeting_id, full_text="", formatted="", stats={}
                    )

                transcript.full_text = " ".join(seg["text"] for seg in segments)
                transcript.formatted = formatted
                transcript.stats = stats
                session.add(transcript)

                # Replace all segments atomically to keep transcript and segments consistent.
                stmt = select(Segment).where(Segment.meeting_id == meeting_id)
                existing_segments = await session.exec(stmt)
                for seg in existing_segments.all():
                    await session.delete(seg)

                for seg_data in segments:
                    segment = Segment(
                        meeting_id=meeting_id,
                        speaker=seg_data["speaker"],
                        text=seg_data["text"],
                        start_time=seg_data["start"],
                        end_time=seg_data["end"],
                    )
                    session.add(segment)

                meeting = await session.get(Meeting, meeting_id)
                if meeting:
                    meeting.status = "completed"
                    meeting.updated_at = datetime.now()
                    session.add(meeting)

    async def get(self, meeting_id: int) -> dict | None:
        """Get a meeting by ID."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            return meeting.model_dump() if meeting else None

    async def get_transcript(self, meeting_id: int) -> dict | None:
        """Get transcript for a meeting."""
        async with self.db.session() as session:
            statement = select(Transcript).where(Transcript.meeting_id == meeting_id)
            results = await session.exec(statement)
            transcript = results.first()

            if not transcript:
                return None

            stmt_seg = (
                select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_time)
            )
            results_seg = await session.exec(stmt_seg)
            segments = results_seg.all()

            result = transcript.model_dump()
            result["segments"] = [s.model_dump() for s in segments]
            return result

    async def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List all meetings."""
        async with self.db.session() as session:
            statement = select(Meeting).order_by(desc(Meeting.date)).offset(offset).limit(limit)
            results = await session.exec(statement)
            meetings = results.all()

            return [m.model_dump() for m in meetings]

    async def update_segment_text(self, segment_id: int, text: str) -> bool:
        """Update a segment's text."""
        async with self.db.session() as session:
            segment = await session.get(Segment, segment_id)
            if not segment:
                return False
            segment.text = text
            session.add(segment)
            await session.commit()
            return True

    async def update_speaker(self, meeting_id: int, old_name: str, new_name: str) -> int:
        """Update all occurrences of a speaker name in a meeting."""
        from sqlmodel import update

        statement = (
            update(Segment)
            .where(Segment.meeting_id == meeting_id)
            .where(Segment.speaker == old_name)
            .values(speaker=new_name)
        )

        async with self.db.session() as session:
            result = await session.exec(statement)
            await session.commit()
            return result.rowcount

    async def delete(self, meeting_id: int) -> bool:
        """Delete a meeting and all related data (cascade handles children)."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            if not meeting:
                return False
            await session.delete(meeting)
            await session.commit()
            return True

    async def save_extracted_data(self, meeting_id: int, data: dict):
        """Save extracted data for a meeting."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            if meeting:
                meeting.extracted_data = data
                meeting.updated_at = datetime.now()
                session.add(meeting)
                await session.commit()
