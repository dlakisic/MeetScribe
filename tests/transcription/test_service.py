"""Transcription service orchestration tests."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.app.transcription.gpu_waker import GPUWaker
from backend.app.transcription.result import TranscriptionResult
from backend.app.transcription.service import TranscriptionService


@pytest.fixture
def gpu_client():
    mock = AsyncMock()
    mock.base_url = "http://gpu:5555"
    return mock


@pytest.fixture
def fallback():
    return AsyncMock()


@pytest.fixture
def gpu_waker():
    return AsyncMock(spec=GPUWaker)


@pytest.mark.asyncio
async def test_gpu_success(gpu_client, fallback):
    """When GPU is available and succeeds, use GPU result."""
    gpu_client.is_gpu_available.return_value = True
    gpu_client.transcribe.return_value = TranscriptionResult(
        success=True, segments=[{"speaker": "A", "text": "hi"}]
    )

    svc = TranscriptionService(gpu_client, fallback)
    result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-1")

    assert result.success
    gpu_client.transcribe.assert_awaited_once()
    fallback.transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_gpu_unavailable_uses_fallback(gpu_client, fallback):
    """When GPU is unavailable, fall back to CPU."""
    gpu_client.is_gpu_available.return_value = False
    fallback.transcribe.return_value = TranscriptionResult(
        success=True, segments=[{"speaker": "B", "text": "fallback"}]
    )

    svc = TranscriptionService(gpu_client, fallback)
    result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-2")

    assert result.success
    gpu_client.transcribe.assert_not_awaited()
    fallback.transcribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_gpu_fails_uses_fallback(gpu_client, fallback):
    """When GPU is available but fails, fall back to CPU."""
    gpu_client.is_gpu_available.return_value = True
    gpu_client.transcribe.return_value = TranscriptionResult(success=False, error="GPU OOM")
    fallback.transcribe.return_value = TranscriptionResult(success=True, segments=[])

    svc = TranscriptionService(gpu_client, fallback)
    result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-3")

    assert result.success
    fallback.transcribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_fallback_returns_error(gpu_client):
    """When GPU unavailable and no fallback, return error."""
    gpu_client.is_gpu_available.return_value = False

    svc = TranscriptionService(gpu_client, fallback=None)
    result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-4")

    assert not result.success
    assert "unavailable" in result.error.lower()


@pytest.mark.asyncio
async def test_waker_called_when_gpu_down(gpu_client, fallback, gpu_waker):
    """GPUWaker is called when GPU is not available."""
    gpu_client.is_gpu_available.return_value = False
    gpu_waker.try_wake.return_value = True
    gpu_client.transcribe.return_value = TranscriptionResult(success=True, segments=[])

    svc = TranscriptionService(gpu_client, fallback, gpu_waker)
    result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-5")

    gpu_waker.try_wake.assert_awaited_once_with("job-5")
    assert result.success
