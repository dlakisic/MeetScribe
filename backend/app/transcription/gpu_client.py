"""HTTP client for the remote GPU transcription worker."""

import asyncio
import json
import time
from contextlib import ExitStack
from pathlib import Path

import httpx

from ..config import Config
from ..core.logging import get_logger
from .result import TranscriptionResult

log = get_logger("gpu_client")


class GPUClient:
    """HTTP client for the remote GPU transcription worker.

    Uses a fire-and-forget model: POST /transcribe returns 202 with a job_id,
    then we poll GET /jobs/{job_id} until completion.
    """

    def __init__(self, config: Config):
        self.gpu = config.gpu
        self.base_url = f"http://{self.gpu.host}:{self.gpu.worker_port}"
        self._auth_headers = (
            {"X-Worker-Token": self.gpu.worker_token} if self.gpu.worker_token else {}
        )

    async def is_gpu_available(self) -> bool:
        """Check if the GPU worker is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health", headers=self._auth_headers)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("status") == "ok"
                return False
        except Exception:
            return False

    async def transcribe(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
    ) -> TranscriptionResult:
        """Submit files to GPU worker and poll for result.

        Supports both async workers (202 + polling) and legacy workers (200 direct).
        """
        job_id = metadata.get("job_id", "unknown")
        request_id = metadata.get("request_id")

        submit_result = await self._submit(mic_path, tab_path, metadata, job_id, request_id)
        if submit_result is None:
            return TranscriptionResult(success=False, error="Failed to submit to GPU worker")

        # Legacy worker returned result directly
        if isinstance(submit_result, TranscriptionResult):
            return submit_result

        # Async worker returned job_id — poll for result
        return await self._poll_until_complete(submit_result, job_id, request_id)

    async def _submit(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
        job_id: str,
        request_id: str | None,
    ) -> str | TranscriptionResult | None:
        """Submit files to worker.

        Returns:
            str: worker job_id (async worker, 202)
            TranscriptionResult: direct result (legacy worker, 200)
            None: submission failed
        """
        try:
            # Use full timeout for legacy compat (old worker blocks until done)
            timeout = httpx.Timeout(self.gpu.submit_timeout, read=self.gpu.timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                with ExitStack() as stack:
                    files = {}
                    if mic_path:
                        f = stack.enter_context(open(mic_path, "rb"))
                        files["mic_file"] = (mic_path.name, f, "audio/webm")
                    if tab_path:
                        f = stack.enter_context(open(tab_path, "rb"))
                        files["tab_file"] = (tab_path.name, f, "audio/webm")

                    data = {"metadata": json.dumps(metadata)}
                    headers = dict(self._auth_headers)
                    if request_id:
                        headers["X-Request-ID"] = str(request_id)

                    log.info(
                        f"[{job_id}] Submitting transcription to worker",
                        extra={"request_id": request_id, "job_id": job_id},
                    )

                    response = await client.post(
                        f"{self.base_url}/transcribe",
                        files=files,
                        data=data,
                        headers=headers,
                    )

                # Async worker (new protocol)
                if response.status_code == 202:
                    worker_job_id = response.json()["job_id"]
                    log.info(
                        f"[{job_id}] Worker accepted job as {worker_job_id}",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return worker_job_id

                # Legacy worker (sync, returns result directly)
                if response.status_code == 200:
                    result = response.json()
                    log.info(
                        f"[{job_id}] Worker returned result directly (legacy mode)",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(
                        success=True,
                        segments=result.get("segments"),
                        formatted=result.get("formatted"),
                        stats=result.get("stats"),
                    )

                log.error(
                    f"[{job_id}] Worker rejected submission: {response.status_code}",
                    extra={
                        "request_id": request_id,
                        "job_id": job_id,
                        "status_code": response.status_code,
                    },
                )
                return None

        except Exception as e:
            log.error(
                f"[{job_id}] Failed to submit to worker: {e}",
                extra={"request_id": request_id, "job_id": job_id},
            )
            return None

    async def _poll_until_complete(
        self,
        worker_job_id: str,
        job_id: str,
        request_id: str | None,
    ) -> TranscriptionResult:
        """Poll GET /jobs/{worker_job_id} until completed or timeout."""
        deadline = time.monotonic() + self.gpu.timeout
        last_step = ""

        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                await asyncio.sleep(self.gpu.poll_interval)

                try:
                    resp = await client.get(
                        f"{self.base_url}/jobs/{worker_job_id}",
                        headers=self._auth_headers,
                    )
                except (httpx.TimeoutException, httpx.ConnectError) as e:
                    log.warning(
                        f"[{job_id}] Poll error: {e}, retrying...",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    continue

                if resp.status_code == 404:
                    log.error(
                        f"[{job_id}] Worker lost track of job (possible restart)",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(
                        success=False,
                        error="Worker lost track of job (possible restart)",
                    )

                if resp.status_code in (401, 403):
                    log.error(
                        f"[{job_id}] Worker auth error: {resp.status_code}",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(
                        success=False,
                        error=f"Worker authentication failed ({resp.status_code})",
                    )

                if resp.status_code != 200:
                    log.warning(
                        f"[{job_id}] Unexpected poll status {resp.status_code}, retrying...",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    continue

                data = resp.json()
                status = data["status"]

                # Log progress changes
                current_step = data.get("progress_step", "")
                if current_step and current_step != last_step:
                    log.info(
                        f"[{job_id}] Worker progress: {data.get('progress_detail', current_step)}",
                        extra={"request_id": request_id, "job_id": job_id, "step": current_step},
                    )
                    last_step = current_step

                if status == "completed":
                    result = data["result"]
                    log.info(
                        f"[{job_id}] Worker transcription completed",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(
                        success=True,
                        segments=result.get("segments"),
                        formatted=result.get("formatted"),
                        stats=result.get("stats"),
                    )
                elif status == "failed":
                    error = data.get("error", "Worker job failed")
                    log.error(
                        f"[{job_id}] Worker transcription failed: {error}",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(success=False, error=error)

        log.error(
            f"[{job_id}] Worker polling timeout after {self.gpu.timeout}s",
            extra={"request_id": request_id, "job_id": job_id},
        )
        return TranscriptionResult(success=False, error="GPU worker timeout (polling)")
