"""Persistent JobStore tests."""

from datetime import datetime

import pytest

from backend.app.database import Database
from backend.app.repositories.meeting_repository import MeetingRepository
from backend.app.services.job_store import JobStore


@pytest.mark.asyncio
async def test_job_survives_reconnect(tmp_path):
    """Job created before disconnect should be available after reconnect."""
    db_path = tmp_path / "persist.db"

    db1 = Database(db_path)
    await db1.connect()

    repo = MeetingRepository(db1)
    mid = await repo.create(title="Test", date=datetime.now())

    store1 = JobStore(db1)
    await store1.create_job("persist-1", meeting_id=mid)
    await store1.update_status("persist-1", "completed")
    await db1.close()

    db2 = Database(db_path)
    await db2.connect()
    store2 = JobStore(db2)

    job = await store2.get_job("persist-1")
    assert job is not None
    assert job["status"] == "completed"
    await db2.close()
