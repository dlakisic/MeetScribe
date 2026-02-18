"""Tests for persistent JobStore."""

from datetime import datetime

import pytest

from backend.app.services.job_store import JobStore


@pytest.fixture
async def job_store(test_db):
    return JobStore(test_db)


@pytest.fixture
async def meeting_id(test_repo):
    """Create a meeting to satisfy FK constraint on jobs."""
    return await test_repo.create(title="Test", date=datetime.now(), platform="Zoom")


@pytest.mark.asyncio
async def test_create_job(job_store, meeting_id):
    await job_store.create_job("job-1", meeting_id=meeting_id)
    job = await job_store.get_job("job-1")
    assert job is not None
    assert job["status"] == "queued"
    assert job["meeting_id"] == meeting_id


@pytest.mark.asyncio
async def test_update_status(job_store, meeting_id):
    await job_store.create_job("job-1", meeting_id=meeting_id)
    await job_store.update_status("job-1", "processing")

    job = await job_store.get_job("job-1")
    assert job["status"] == "processing"


@pytest.mark.asyncio
async def test_update_with_result(job_store, meeting_id):
    await job_store.create_job("job-1", meeting_id=meeting_id)
    await job_store.update_status("job-1", "completed", result={"segments_count": 10})

    job = await job_store.get_job("job-1")
    assert job["status"] == "completed"
    assert job["result"]["segments_count"] == 10


@pytest.mark.asyncio
async def test_update_with_error(job_store, meeting_id):
    await job_store.create_job("job-1", meeting_id=meeting_id)
    await job_store.update_status("job-1", "failed", error="GPU exploded")

    job = await job_store.get_job("job-1")
    assert job["status"] == "failed"
    assert job["error"] == "GPU exploded"


@pytest.mark.asyncio
async def test_get_unknown_job(job_store):
    assert await job_store.get_job("nonexistent") is None


@pytest.mark.asyncio
async def test_cleanup_old_jobs(job_store, meeting_id):
    await job_store.create_job("old-job", meeting_id=meeting_id)
    await job_store.update_status("old-job", "completed")

    # Cleanup with 0 hours = delete everything completed
    deleted = await job_store.cleanup_old_jobs(max_age_hours=0)
    assert deleted == 1
    assert await job_store.get_job("old-job") is None


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_jobs(job_store, meeting_id):
    await job_store.create_job("recent-job", meeting_id=meeting_id)
    await job_store.update_status("recent-job", "completed")

    # Cleanup with 24h = keep recent jobs
    deleted = await job_store.cleanup_old_jobs(max_age_hours=24)
    assert deleted == 0
    assert await job_store.get_job("recent-job") is not None
