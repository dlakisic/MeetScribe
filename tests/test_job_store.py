"""Tests for JobStore in-memory job tracking."""

from backend.app.services.job_store import JobStore


def test_create_job():
    store = JobStore()
    store.create_job("job-1", meeting_id=42)

    job = store.get_job("job-1")
    assert job is not None
    assert job["status"] == "queued"
    assert job["meeting_id"] == 42


def test_update_status():
    store = JobStore()
    store.create_job("job-1", meeting_id=1)
    store.update_status("job-1", "processing")

    assert store.get_job("job-1")["status"] == "processing"


def test_update_with_result():
    store = JobStore()
    store.create_job("job-1", meeting_id=1)
    store.update_status("job-1", "completed", result={"segments_count": 10})

    job = store.get_job("job-1")
    assert job["status"] == "completed"
    assert job["result"]["segments_count"] == 10


def test_update_with_error():
    store = JobStore()
    store.create_job("job-1", meeting_id=1)
    store.update_status("job-1", "failed", error="GPU exploded")

    job = store.get_job("job-1")
    assert job["status"] == "failed"
    assert job["error"] == "GPU exploded"


def test_get_unknown_job():
    store = JobStore()
    assert store.get_job("nonexistent") is None
