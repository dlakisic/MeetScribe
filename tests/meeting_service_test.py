from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.schemas.extraction import ExtractedData, MeetingSummary
from backend.app.services.meeting_service import MeetingService
from backend.app.transcription.result import TranscriptionResult


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_transcriber():
    return AsyncMock()


@pytest.fixture
def mock_job_store():
    return MagicMock()


@pytest.fixture
def mock_extraction_service():
    return AsyncMock()


@pytest.fixture
def service(mock_repo, mock_transcriber, mock_job_store, mock_extraction_service):
    return MeetingService(
        repo=mock_repo,
        transcriber=mock_transcriber,
        job_store=mock_job_store,
        extraction_service=mock_extraction_service,
    )


@pytest.mark.asyncio
async def test_create_meeting(service, mock_repo):
    """Test creating a meeting record."""
    mock_repo.create.return_value = 123

    meeting_id = await service.create_meeting(title="Test Meeting", date=datetime.now())

    assert meeting_id == 123
    mock_repo.create.assert_called_once()


@pytest.mark.asyncio
async def test_process_upload_success(
    service, mock_transcriber, mock_repo, mock_extraction_service, mock_job_store
):
    """Test successful end-to-end processing of a meeting upload."""

    # Mock transcription result
    mock_transcriber.transcribe.return_value = TranscriptionResult(
        success=True,
        segments=[{"start": 0, "end": 10, "text": "Hello"}],
        formatted="Hello world",
        stats={},
    )

    # Mock extraction result
    mock_extraction_service.extract_from_transcript.return_value = ExtractedData(
        summary=MeetingSummary(abstract="Summary", topics=[], sentiment="neutral"),
        action_items=[],
        decisions=[],
    )

    await service.process_upload(
        job_id="job-123",
        meeting_id=1,
        mic_path=Path("/tmp/mic.webm"),
        tab_path=Path("/tmp/tab.webm"),
        metadata={},
    )

    # Verify flow
    mock_job_store.update_status.assert_any_call("job-123", "processing")
    mock_transcriber.transcribe.assert_called_once()
    mock_repo.save_transcript.assert_called_once()
    mock_extraction_service.extract_from_transcript.assert_called_once()
    mock_repo.save_extracted_data.assert_called_once()
    mock_job_store.update_status.assert_called_with(
        "job-123",
        "completed",
        result={"meeting_id": 1, "segments_count": 1, "used_fallback": False},
    )


@pytest.mark.asyncio
async def test_process_upload_transcription_failure(
    service, mock_transcriber, mock_repo, mock_job_store
):
    """Test handling of transcription failure."""

    # Mock failure
    mock_transcriber.transcribe.return_value = TranscriptionResult(
        success=False, error="GPU Explosion"
    )

    await service.process_upload(
        job_id="job-fail", meeting_id=2, mic_path=None, tab_path=None, metadata={}
    )

    # Verify error handling
    mock_repo.update_status.assert_called_with(2, "failed")
    mock_job_store.update_status.assert_called_with("job-fail", "failed", error="GPU Explosion")
