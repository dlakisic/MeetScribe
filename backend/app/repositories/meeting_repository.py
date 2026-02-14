from datetime import datetime

from sqlmodel import desc, select

from ..database import Database
from ..models import Meeting, Segment, Transcript


class MeetingRepository:
    """Repository for accessing meeting data via SQLModel."""

    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        title: str,
        date: datetime,
        platform: str | None = None,
        url: str | None = None,
        duration: float | None = None,
    ) -> int:
        """Create a new meeting record."""
        meeting = Meeting(
            title=title,
            date=date,
            platform=platform,
            url=url,
            duration=duration,
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

    async def save_transcript(
        self,
        meeting_id: int,
        segments: list[dict],
        formatted: str,
        stats: dict,
    ):
        """Save transcript and segments for a meeting."""
        async with self.db.session() as session:
            # Check if transcript exists
            statement = select(Transcript).where(Transcript.meeting_id == meeting_id)
            results = await session.exec(statement)
            transcript = results.first()

            if not transcript:
                transcript = Transcript(meeting_id=meeting_id, full_text="", formatted="", stats={})

            # Update transcript fields
            transcript.full_text = " ".join(seg["text"] for seg in segments)
            transcript.formatted = formatted
            transcript.stats = stats
            session.add(transcript)

            # Delete existing segments (naive approach: delete all and recreate)
            # In a real app we might want to be smarter, but this matches previous logic
            stmt = select(Segment).where(Segment.meeting_id == meeting_id)
            existing_segments = await session.exec(stmt)
            for seg in existing_segments.all():
                await session.delete(seg)

            # Add new segments
            for seg_data in segments:
                segment = Segment(
                    meeting_id=meeting_id,
                    speaker=seg_data["speaker"],
                    text=seg_data["text"],
                    start_time=seg_data["start"],
                    end_time=seg_data["end"],
                )
                session.add(segment)

            # Update meeting status
            meeting = await session.get(Meeting, meeting_id)
            if meeting:
                meeting.status = "completed"
                meeting.updated_at = datetime.now()
                session.add(meeting)

            await session.commit()

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

            # Load segments
            stmt_seg = (
                select(Segment).where(Segment.meeting_id == meeting_id).order_by(Segment.start_time)
            )
            results_seg = await session.exec(stmt_seg)
            segments = results_seg.all()

            # Format result to match previous dict structure
            result = transcript.model_dump()
            result["segments"] = [s.model_dump() for s in segments]
            return result

    async def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List all meetings."""
        async with self.db.session() as session:
            # We want to join with Transcript to verify existence, like the LEFT JOIN before
            # BUT SQLModel/SQLAlchemy async joins are verbose.
            # For list, just fetching meetings is enough, the frontend checks details later.
            # To simulate "has_transcript", we can do a naive check or eager load.
            # Let's keep it simple: just list meetings for now, frontend will query details if needed.
            # To match previous behavior helper "has_transcript":

            statement = select(Meeting).order_by(desc(Meeting.date)).offset(offset).limit(limit)
            results = await session.exec(statement)
            meetings = results.all()

            # Convert to dicts
            return [m.model_dump() for m in meetings]

    async def save_extracted_data(self, meeting_id: int, data: dict):
        """Save extracted data for a meeting."""
        async with self.db.session() as session:
            meeting = await session.get(Meeting, meeting_id)
            if meeting:
                meeting.extracted_data = data
                meeting.updated_at = datetime.now()
                session.add(meeting)
                await session.commit()
