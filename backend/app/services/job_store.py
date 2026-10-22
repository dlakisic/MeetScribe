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

    async def update_progress(self, job_id: str, step: str, percent: int | None = None) -> None:
        async with self._db.session() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            row = (await session.exec(stmt)).first()
            if not row:
                return
            row.progress_step = step
            row.progress_percent = percent
            row.updated_at = datetime.now()
            session.add(row)
            await session.commit()

    async def get_job(self, job_id: str) -> dict | None:
        async with self._db.session() as session:
            stmt = select(Job).where(Job.job_id == job_id)
            job = (await session.exec(stmt)).first()
            return self._to_dict(job) if job else None

    async def list_active(self) -> list[dict]:
        """Jobs still queued or processing, oldest first."""
        async with self._db.session() as session:
            stmt = (
                select(Job).where(Job.status.in_(["queued", "processing"])).order_by(Job.created_at)
            )
            return [self._to_dict(job) for job in (await session.exec(stmt)).all()]

    @staticmethod
    def _to_dict(job: Job) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "meeting_id": job.meeting_id,
            "created_at": job.created_at.isoformat(),
            "progress_step": job.progress_step,
            "progress_percent": job.progress_percent,
            "result": job.result,
            "error": job.error,
        }

    async def fail_interrupted_jobs(self) -> list[int]:
        """Mark jobs left queued/processing by a previous run as failed.

        Background tasks don't survive a restart, so these jobs would otherwise
        stay pending forever. Returns the affected meeting IDs.
        """
        async with self._db.session() as session:
            stmt = select(Job).where(Job.status.in_(["queued", "processing"]))
            jobs = (await session.exec(stmt)).all()
            for job in jobs:
                job.status = "failed"
                job.error = "Interrupted by server restart"
                job.updated_at = datetime.now()
                session.add(job)
            await session.commit()
            if jobs:
                log.warning(f"Marked {len(jobs)} interrupted jobs as failed")
            return [job.meeting_id for job in jobs]

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
