"""Sprint 2 tests — ABC compliance, DI, GPUWaker, model reuse."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.interfaces import (
    AbstractExtractionService,
    AbstractJobStore,
    AbstractMeetingRepository,
    AbstractTranscriber,
)
from backend.app.repositories.meeting_repository import MeetingRepository
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.job_store import JobStore
from backend.app.services.meeting_service import MeetingService
from backend.app.transcription.gpu_waker import GPUWaker
from backend.app.transcription.result import TranscriptionResult
from backend.app.transcription.service import TranscriptionService

# --- ABC compliance ---


class TestABCCompliance:
    """Verify concrete classes implement their ABCs."""

    def test_repo_implements_abc(self):
        assert issubclass(MeetingRepository, AbstractMeetingRepository)

    def test_transcription_service_implements_abc(self):
        assert issubclass(TranscriptionService, AbstractTranscriber)

    def test_extraction_service_implements_abc(self):
        assert issubclass(ExtractionService, AbstractExtractionService)

    def test_job_store_implements_abc(self):
        assert issubclass(JobStore, AbstractJobStore)


# --- TranscriptionService DI ---


class TestTranscriptionServiceDI:
    """Test TranscriptionService with injected mocks."""

    @pytest.fixture
    def gpu_client(self):
        mock = AsyncMock()
        mock.base_url = "http://gpu:5555"
        return mock

    @pytest.fixture
    def fallback(self):
        return AsyncMock()

    @pytest.fixture
    def gpu_waker(self):
        return AsyncMock(spec=GPUWaker)

    @pytest.mark.asyncio
    async def test_gpu_success(self, gpu_client, fallback):
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
    async def test_gpu_unavailable_uses_fallback(self, gpu_client, fallback):
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
    async def test_gpu_fails_uses_fallback(self, gpu_client, fallback):
        """When GPU is available but fails, fall back to CPU."""
        gpu_client.is_gpu_available.return_value = True
        gpu_client.transcribe.return_value = TranscriptionResult(success=False, error="GPU OOM")
        fallback.transcribe.return_value = TranscriptionResult(success=True, segments=[])

        svc = TranscriptionService(gpu_client, fallback)
        result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-3")

        assert result.success
        fallback.transcribe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_fallback_returns_error(self, gpu_client):
        """When GPU unavailable and no fallback, return error."""
        gpu_client.is_gpu_available.return_value = False

        svc = TranscriptionService(gpu_client, fallback=None)
        result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-4")

        assert not result.success
        assert "unavailable" in result.error.lower()

    @pytest.mark.asyncio
    async def test_waker_called_when_gpu_down(self, gpu_client, fallback, gpu_waker):
        """GPUWaker is called when GPU is not available."""
        gpu_client.is_gpu_available.return_value = False
        gpu_waker.try_wake.return_value = True
        gpu_client.transcribe.return_value = TranscriptionResult(success=True, segments=[])

        svc = TranscriptionService(gpu_client, fallback, gpu_waker)
        result = await svc.transcribe(Path("/mic.wav"), Path("/tab.wav"), {}, "job-5")

        gpu_waker.try_wake.assert_awaited_once_with("job-5")
        assert result.success


# --- GPUWaker ---


class TestGPUWaker:
    """Test GPUWaker polling logic."""

    @pytest.mark.asyncio
    async def test_wake_success(self):
        """Smart plug ON → GPU becomes available before timeout."""
        smart_plug = AsyncMock()
        smart_plug.is_configured = MagicMock(return_value=True)
        smart_plug.turn_on.return_value = True

        gpu_client = AsyncMock()
        # First check: not ready, second check: ready
        gpu_client.is_gpu_available.side_effect = [False, True]

        waker = GPUWaker(smart_plug, gpu_client, boot_wait_time=30, check_interval=1)

        with patch("backend.app.transcription.gpu_waker.asyncio.sleep", new_callable=AsyncMock):
            result = await waker.try_wake("job-w1")

        assert result is True
        smart_plug.turn_on.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wake_timeout(self):
        """GPU never comes up → returns False."""
        smart_plug = AsyncMock()
        smart_plug.is_configured = MagicMock(return_value=True)
        smart_plug.turn_on.return_value = True

        gpu_client = AsyncMock()
        gpu_client.is_gpu_available.return_value = False

        waker = GPUWaker(smart_plug, gpu_client, boot_wait_time=3, check_interval=1)

        with patch("backend.app.transcription.gpu_waker.asyncio.sleep", new_callable=AsyncMock):
            result = await waker.try_wake("job-w2")

        assert result is False

    @pytest.mark.asyncio
    async def test_wake_not_configured(self):
        """If smart plug not configured, return False immediately."""
        smart_plug = AsyncMock()
        smart_plug.is_configured = MagicMock(return_value=False)

        gpu_client = AsyncMock()
        waker = GPUWaker(smart_plug, gpu_client, boot_wait_time=30)

        result = await waker.try_wake("job-w3")

        assert result is False
        smart_plug.turn_on.assert_not_awaited()


# --- MeetingService.is_gpu_available ---


class TestMeetingServiceGPU:
    """Test the is_gpu_available delegation."""

    @pytest.mark.asyncio
    async def test_is_gpu_available_delegates(self):
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
    async def test_is_gpu_available_returns_false(self):
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
