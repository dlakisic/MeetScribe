"""GPU waker polling tests."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.transcription.gpu_waker import GPUWaker


@pytest.mark.asyncio
async def test_wake_success():
    """Smart plug ON -> GPU becomes available before timeout."""
    smart_plug = AsyncMock()
    smart_plug.is_configured = MagicMock(return_value=True)
    smart_plug.turn_on.return_value = True

    gpu_client = AsyncMock()
    gpu_client.is_gpu_available.side_effect = [False, True]

    waker = GPUWaker(smart_plug, gpu_client, boot_wait_time=30, check_interval=1)

    with patch("backend.app.transcription.gpu_waker.asyncio.sleep", new_callable=AsyncMock):
        result = await waker.try_wake("job-w1")

    assert result is True
    smart_plug.turn_on.assert_awaited_once()


@pytest.mark.asyncio
async def test_wake_timeout():
    """GPU never comes up -> returns False."""
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
async def test_wake_not_configured():
    """If smart plug not configured, return False immediately."""
    smart_plug = AsyncMock()
    smart_plug.is_configured = MagicMock(return_value=False)

    gpu_client = AsyncMock()
    waker = GPUWaker(smart_plug, gpu_client, boot_wait_time=30)

    result = await waker.try_wake("job-w3")

    assert result is False
    smart_plug.turn_on.assert_not_awaited()
