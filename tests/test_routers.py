"""Tests for API routes using httpx AsyncClient."""

from datetime import datetime

import pytest


@pytest.mark.asyncio
async def test_root(client):
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "MeetScribe"
    assert "version" in data


@pytest.mark.asyncio
async def test_list_transcripts_empty(client):
    resp = await client.get("/api/transcripts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meetings"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_list_transcripts_with_data(client, test_app):
    """Seed a meeting via the repo and verify it shows in the list."""
    service = test_app.state.meeting_service
    await service.create_meeting(title="Listed Meeting", date=datetime(2026, 1, 1))

    resp = await client.get("/api/transcripts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["meetings"][0]["title"] == "Listed Meeting"


@pytest.mark.asyncio
async def test_get_transcript(client, test_app):
    service = test_app.state.meeting_service
    mid = await service.create_meeting(title="Detail Test", date=datetime(2026, 1, 1))

    resp = await client.get(f"/api/transcripts/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["meeting"]["title"] == "Detail Test"


@pytest.mark.asyncio
async def test_get_transcript_not_found(client):
    resp = await client.get("/api/transcripts/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_meeting(client, test_app):
    service = test_app.state.meeting_service
    mid = await service.create_meeting(title="Old Title", date=datetime(2026, 1, 1))

    resp = await client.patch(f"/api/meetings/{mid}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_delete_meeting(client, test_app):
    service = test_app.state.meeting_service
    mid = await service.create_meeting(title="To Delete", date=datetime(2026, 1, 1))

    resp = await client.delete(f"/api/meetings/{mid}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify it's gone
    resp2 = await client.get(f"/api/transcripts/{mid}")
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_meeting_not_found(client):
    resp = await client.delete("/api/meetings/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_no_files(client):
    """Upload with no audio files should return 400."""
    resp = await client.post(
        "/api/upload",
        data={"metadata": '{"title": "Test", "date": "2026-01-01T00:00:00"}'},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_job_status(client, test_app):
    """Test job status endpoint."""
    job_store = test_app.state.job_store
    job_store.create_job("test-job", meeting_id=1)
    job_store.update_status("test-job", "completed", result={"meeting_id": 1})

    resp = await client.get("/api/status/test-job")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_get_job_status_not_found(client):
    resp = await client.get("/api/status/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_segment(client, test_app):
    """Create a meeting with segments, then update one."""
    service = test_app.state.meeting_service
    mid = await service.create_meeting(title="Seg Test", date=datetime(2026, 1, 1))

    # Save transcript with segments
    await service.repo.save_transcript(
        mid,
        [{"speaker": "A", "text": "old", "start": 0, "end": 1}],
        "old",
        {},
    )

    # Get segment ID
    transcript = await service.repo.get_transcript(mid)
    seg_id = transcript["segments"][0]["id"]

    resp = await client.patch(f"/api/segments/{seg_id}", json={"text": "new text"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
