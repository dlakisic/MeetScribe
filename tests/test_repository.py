"""Tests for MeetingRepository with real SQLite database."""

from datetime import datetime

import pytest

from backend.app.repositories.meeting_repository import MeetingRepository


@pytest.mark.asyncio
async def test_create_meeting(test_repo: MeetingRepository):
    meeting_id = await test_repo.create(
        title="My Meeting", date=datetime(2026, 1, 1, 9, 0)
    )
    assert isinstance(meeting_id, int)
    assert meeting_id > 0


@pytest.mark.asyncio
async def test_get_meeting(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Get Test", date=datetime(2026, 1, 1))
    meeting = await test_repo.get(mid)

    assert meeting is not None
    assert meeting["title"] == "Get Test"
    assert meeting["status"] == "processing"


@pytest.mark.asyncio
async def test_get_meeting_not_found(test_repo: MeetingRepository):
    assert await test_repo.get(99999) is None


@pytest.mark.asyncio
async def test_update_status(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Status Test", date=datetime(2026, 1, 1))
    await test_repo.update_status(mid, "completed")

    meeting = await test_repo.get(mid)
    assert meeting["status"] == "completed"


@pytest.mark.asyncio
async def test_update_fields_whitelist(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Fields Test", date=datetime(2026, 1, 1))
    result = await test_repo.update_fields(mid, {"title": "New Title", "platform": "Teams"})

    assert result is True
    meeting = await test_repo.get(mid)
    assert meeting["title"] == "New Title"
    assert meeting["platform"] == "Teams"


@pytest.mark.asyncio
async def test_update_fields_rejects_id(test_repo: MeetingRepository):
    """Fields not in UPDATABLE_FIELDS are silently ignored."""
    mid = await test_repo.create(title="Reject Test", date=datetime(2026, 1, 1))
    await test_repo.update_fields(mid, {"id": 999, "status": "hacked", "title": "Safe"})

    meeting = await test_repo.get(mid)
    assert meeting["id"] == mid  # id unchanged
    assert meeting["status"] == "processing"  # status unchanged
    assert meeting["title"] == "Safe"  # title changed (whitelisted)


@pytest.mark.asyncio
async def test_update_fields_not_found(test_repo: MeetingRepository):
    result = await test_repo.update_fields(99999, {"title": "Ghost"})
    assert result is False


@pytest.mark.asyncio
async def test_save_transcript(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Transcript Test", date=datetime(2026, 1, 1))

    segments = [
        {"speaker": "Alice", "text": "Hello", "start": 0.0, "end": 3.0},
        {"speaker": "Bob", "text": "World", "start": 3.0, "end": 6.0},
    ]
    await test_repo.save_transcript(mid, segments, "formatted text", {"dur": 6.0})

    transcript = await test_repo.get_transcript(mid)
    assert transcript is not None
    assert len(transcript["segments"]) == 2
    assert transcript["segments"][0]["speaker"] == "Alice"
    assert transcript["formatted"] == "formatted text"

    # Status should be updated to completed
    meeting = await test_repo.get(mid)
    assert meeting["status"] == "completed"


@pytest.mark.asyncio
async def test_save_transcript_replace(test_repo: MeetingRepository):
    """Re-saving transcript replaces existing segments."""
    mid = await test_repo.create(title="Replace Test", date=datetime(2026, 1, 1))

    # First save
    await test_repo.save_transcript(
        mid,
        [{"speaker": "A", "text": "old", "start": 0, "end": 1}],
        "old",
        {},
    )

    # Second save — should replace
    await test_repo.save_transcript(
        mid,
        [
            {"speaker": "X", "text": "new1", "start": 0, "end": 2},
            {"speaker": "Y", "text": "new2", "start": 2, "end": 4},
        ],
        "new",
        {},
    )

    transcript = await test_repo.get_transcript(mid)
    assert len(transcript["segments"]) == 2
    assert transcript["segments"][0]["speaker"] == "X"
    assert transcript["formatted"] == "new"


@pytest.mark.asyncio
async def test_delete_cascade(test_repo: MeetingRepository, test_db):
    """Deleting a meeting should cascade to transcript and segments."""
    mid = await test_repo.create(title="Delete Test", date=datetime(2026, 1, 1))
    await test_repo.save_transcript(
        mid,
        [{"speaker": "A", "text": "hi", "start": 0, "end": 1}],
        "hi",
        {},
    )

    result = await test_repo.delete(mid)
    assert result is True

    # Meeting gone
    assert await test_repo.get(mid) is None
    # Transcript gone
    assert await test_repo.get_transcript(mid) is None


@pytest.mark.asyncio
async def test_delete_not_found(test_repo: MeetingRepository):
    assert await test_repo.delete(99999) is False


@pytest.mark.asyncio
async def test_list_meetings(test_repo: MeetingRepository):
    await test_repo.create(title="Meeting A", date=datetime(2026, 1, 1))
    await test_repo.create(title="Meeting B", date=datetime(2026, 1, 2))
    await test_repo.create(title="Meeting C", date=datetime(2026, 1, 3))

    meetings = await test_repo.list(limit=2, offset=0)
    assert len(meetings) == 2
    # Ordered by date desc
    assert meetings[0]["title"] == "Meeting C"
    assert meetings[1]["title"] == "Meeting B"

    # Offset
    meetings2 = await test_repo.list(limit=10, offset=2)
    assert len(meetings2) == 1
    assert meetings2[0]["title"] == "Meeting A"


@pytest.mark.asyncio
async def test_update_segment_text(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Seg Edit", date=datetime(2026, 1, 1))
    await test_repo.save_transcript(
        mid,
        [{"speaker": "A", "text": "old text", "start": 0, "end": 1}],
        "old text",
        {},
    )

    transcript = await test_repo.get_transcript(mid)
    seg_id = transcript["segments"][0]["id"]

    result = await test_repo.update_segment_text(seg_id, "new text")
    assert result is True

    transcript = await test_repo.get_transcript(mid)
    assert transcript["segments"][0]["text"] == "new text"


@pytest.mark.asyncio
async def test_update_speaker(test_repo: MeetingRepository):
    mid = await test_repo.create(title="Speaker Test", date=datetime(2026, 1, 1))
    await test_repo.save_transcript(
        mid,
        [
            {"speaker": "SPEAKER_00", "text": "hello", "start": 0, "end": 1},
            {"speaker": "SPEAKER_00", "text": "world", "start": 1, "end": 2},
            {"speaker": "SPEAKER_01", "text": "hi", "start": 2, "end": 3},
        ],
        "",
        {},
    )

    count = await test_repo.update_speaker(mid, "SPEAKER_00", "Alice")
    assert count == 2

    transcript = await test_repo.get_transcript(mid)
    speakers = [s["speaker"] for s in transcript["segments"]]
    assert speakers == ["Alice", "Alice", "SPEAKER_01"]
