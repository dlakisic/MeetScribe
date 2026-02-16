"""Persistent job store backed by SQLite."""

from datetime import datetime, timedelta

from sqlmodel import select

from ..core.logging import get_logger
from ..database import Database
from ..interfaces import AbstractJobStore
from ..models import Job

log = get_logger("job_store")


class JobStore(AbstractJobStore):
    """Job status tracking persisted to database."""

    def __init__(self, db: Database):
        self._db = db

    async def create_job(self, job_id: str, meeting_id: int) -> None:
        async with self._db.session() as session:
            job = Job(job_id=job_id, meeting_id=meeting_id)
            session.add(job)
            await session.commit()

    async def update_status(
        self, job_id: str, status: str, result: dict | None = None, error: str | None = None
    ) -> None:
        async with self._db.session() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            row = (await session.exec(stmt)).first()
            if not row:
                return
            row.status = status
            row.updated_at = datetime.now()
            if result is not None:
                row.result = result
            if error is not None:
                row.error = error
            session.add(row)
            await session.commit()

    async def get_job(self, job_id: str) -> dict | None:
        async with self._db.session() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            job = (await session.exec(stmt)).first()
            if not job:
                return None
            return {
                "job_id": job.job_id,
                "status": job.status,
                "meeting_id": job.meeting_id,
                "created_at": job.created_at.isoformat(),
                "result": job.result,
                "error": job.error,
            }

    async def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        """Delete completed/failed jobs older than max_age_hours."""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        async with self._db.session() as session:
            stmt = select(Job).where(
                Job.status.in_(["completed", "failed"]),
                Job.created_at < cutoff,
            )
            old_jobs = (await session.exec(stmt)).all()
            for job in old_jobs:
                await session.delete(job)
            await session.commit()
            if old_jobs:
                log.info(f"Cleaned up {len(old_jobs)} old jobs")
            return len(old_jobs)
