"""Tests for API routes using httpx AsyncClient."""

from datetime import datetime

import pytest

from backend.app.routers.upload import _parse_date, _safe_filename


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
    # Need a meeting first (FK constraint)
    repo = test_app.state.meeting_service.repo
    from datetime import datetime
    mid = await repo.create(title="Test", date=datetime.now())
    await job_store.create_job("test-job", meeting_id=mid)
    await job_store.update_status("test-job", "completed", result={"meeting_id": mid})

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


# --- Sprint 1: Security tests ---


class TestSafeFilename:
    """Tests for path traversal prevention."""

    def test_normal_filename(self):
        assert _safe_filename("audio.webm") == "audio.webm"

    def test_path_traversal_dotdot(self):
        assert _safe_filename("../../etc/passwd") == "passwd"

    def test_path_traversal_absolute(self):
        assert _safe_filename("/etc/shadow") == "shadow"

    def test_null_byte(self):
        result = _safe_filename("file\0name.webm")
        assert "\0" not in result

    def test_backslash_traversal(self):
        result = _safe_filename("..\\..\\windows\\system32\\config")
        assert ".." not in result

    def test_empty_filename(self):
        assert _safe_filename("") == "unnamed"


class TestParseDate:
    """Tests for date validation."""

    def test_valid_iso_date(self):
        result = _parse_date("2026-01-15T10:30:00")
        assert result.year == 2026
        assert result.month == 1

    def test_none_returns_now(self):
        result = _parse_date(None)
        assert isinstance(result, datetime)

    def test_empty_returns_now(self):
        result = _parse_date("")
        assert isinstance(result, datetime)

    def test_invalid_date_raises_400(self):
        with pytest.raises(Exception) as exc_info:
            _parse_date("not-a-date")
        assert "400" in str(exc_info.value.status_code)


@pytest.mark.asyncio
async def test_upload_invalid_date(client):
    """Upload with invalid date should return 400."""
    resp = await client.post(
        "/api/upload",
        data={"metadata": '{"title": "Test", "date": "not-a-date"}'},
        files={"mic_file": ("test.webm", b"fake audio", "audio/webm")},
    )
    assert resp.status_code == 400
    assert "date" in resp.json()["detail"].lower()
