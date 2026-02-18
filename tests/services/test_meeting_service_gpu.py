"""Meeting service GPU availability delegation tests."""

from unittest.mock import AsyncMock

import pytest

from backend.app.services.meeting_service import MeetingService


@pytest.mark.asyncio
async def test_is_gpu_available_delegates_true():
    mock_transcriber = AsyncMock()
    mock_transcriber.is_gpu_available.return_value = True

    svc = MeetingService(
        repo=AsyncMock(),
        transcriber=mock_transcriber,
        job_store=AsyncMock(),
        extraction_service=AsyncMock(),
    )

    result = await svc.is_gpu_available()
    assert result is True


@pytest.mark.asyncio
async def test_is_gpu_available_delegates_false():
    mock_transcriber = AsyncMock()
    mock_transcriber.is_gpu_available.return_value = False

    svc = MeetingService(
        repo=AsyncMock(),
        transcriber=mock_transcriber,
        job_store=AsyncMock(),
        extraction_service=AsyncMock(),
    )

    result = await svc.is_gpu_available()
    assert result is False
