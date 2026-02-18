"""Tests for GPU client async submit + poll protocol."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.config import Config, GPUWorkerConfig
from backend.app.transcription.gpu_client import GPUClient


def _make_client(**gpu_overrides) -> GPUClient:
    defaults = dict(
        host="gpu-test",
        worker_port=8001,
        timeout=10,
        poll_interval=0.05,
        submit_timeout=5.0,
    )
    defaults.update(gpu_overrides)
    gpu = GPUWorkerConfig(**defaults)
    config = Config(gpu=gpu)
    return GPUClient(config)


def _meta(job_id: str = "job-1") -> dict:
    return {"job_id": job_id}


# ---------------------------------------------------------------------------
# Submit phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_202_starts_polling():
    """Async worker returns 202 -> client should poll /jobs/{id}."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})
    poll_resp = httpx.Response(
        200,
        json={
            "job_id": "job-1",
            "status": "completed",
            "progress_step": "saving",
            "progress_detail": "Saving results",
            "result": {"segments": [{"text": "hi"}], "formatted": "hi", "stats": {}},
        },
    )

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            return_value=poll_resp,
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert result.success
    assert result.segments == [{"text": "hi"}]


@pytest.mark.asyncio
async def test_submit_200_legacy_compat():
    """Legacy worker returns 200 -> client should use result directly, no polling."""
    client = _make_client()

    legacy_resp = httpx.Response(
        200,
        json={"segments": [{"text": "legacy"}], "formatted": "legacy", "stats": {}},
    )

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=legacy_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
        ) as mock_get,
    ):
        result = await client.transcribe(None, None, _meta())

    assert result.success
    assert result.formatted == "legacy"
    mock_get.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_failure_returns_error():
    """Worker returns 500 on submit -> immediate failure."""
    client = _make_client()

    with patch.object(
        httpx.AsyncClient,
        "post",
        new_callable=AsyncMock,
        return_value=httpx.Response(500, text="Internal error"),
    ):
        result = await client.transcribe(None, None, _meta())

    assert not result.success
    assert "Failed to submit" in result.error


# ---------------------------------------------------------------------------
# Polling phase
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_progress_then_complete():
    """Poll shows progress steps then completes."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})
    poll_responses = [
        httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "status": "processing",
                "progress_step": "transcribing_tab",
                "progress_detail": "Transcribing tab",
            },
        ),
        httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "status": "processing",
                "progress_step": "merging",
                "progress_detail": "Merging",
            },
        ),
        httpx.Response(
            200,
            json={
                "job_id": "job-1",
                "status": "completed",
                "progress_step": "saving",
                "progress_detail": "Done",
                "result": {"segments": [], "formatted": "", "stats": {}},
            },
        ),
    ]

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            side_effect=poll_responses,
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert result.success


@pytest.mark.asyncio
async def test_poll_job_failed():
    """Worker job fails -> client returns failure."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})
    poll_resp = httpx.Response(
        200,
        json={
            "job_id": "job-1",
            "status": "failed",
            "progress_step": "",
            "progress_detail": "",
            "error": "OOM",
        },
    )

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            return_value=poll_resp,
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert not result.success
    assert "OOM" in result.error


@pytest.mark.asyncio
async def test_poll_404_worker_restart():
    """Worker returns 404 -> job lost, immediate failure."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            return_value=httpx.Response(404),
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert not result.success
    assert "restart" in result.error.lower()


@pytest.mark.asyncio
async def test_poll_401_fails_fast():
    """Worker returns 401 -> immediate auth failure, no retry loop."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            return_value=httpx.Response(401),
        ) as mock_get,
    ):
        result = await client.transcribe(None, None, _meta())

    assert not result.success
    assert "authentication" in result.error.lower()
    assert mock_get.await_count == 1


@pytest.mark.asyncio
async def test_poll_timeout():
    """Polling exceeds deadline -> timeout error."""
    client = _make_client(timeout=0.2, poll_interval=0.05)

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})
    processing_resp = httpx.Response(
        200,
        json={
            "job_id": "job-1",
            "status": "processing",
            "progress_step": "transcribing_tab",
            "progress_detail": "Still working",
        },
    )

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            return_value=processing_resp,
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert not result.success
    assert "timeout" in result.error.lower()


@pytest.mark.asyncio
async def test_poll_transient_network_error_retries():
    """Transient network errors during polling are retried."""
    client = _make_client()

    submit_resp = httpx.Response(202, json={"job_id": "job-1", "status": "queued"})
    completed_resp = httpx.Response(
        200,
        json={
            "job_id": "job-1",
            "status": "completed",
            "progress_step": "",
            "progress_detail": "",
            "result": {"segments": [], "formatted": "", "stats": {}},
        },
    )

    call_count = 0

    async def get_with_errors(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise httpx.ConnectError("Connection refused")
        return completed_resp

    with (
        patch.object(
            httpx.AsyncClient,
            "post",
            new_callable=AsyncMock,
            return_value=submit_resp,
        ),
        patch.object(
            httpx.AsyncClient,
            "get",
            side_effect=get_with_errors,
        ),
    ):
        result = await client.transcribe(None, None, _meta())

    assert result.success
    assert call_count == 3
