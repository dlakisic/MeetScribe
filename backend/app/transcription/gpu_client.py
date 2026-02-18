"""HTTP client for the remote GPU transcription worker."""

import json
from contextlib import ExitStack
from pathlib import Path

import httpx

from ..config import Config
from ..core.logging import get_logger
from .result import TranscriptionResult

log = get_logger("gpu_client")


class GPUClient:
    """HTTP client for the remote GPU transcription worker."""

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
        """Send files to GPU worker and get transcription result."""
        job_id = metadata.get("job_id", "unknown")
        request_id = metadata.get("request_id")
        try:
            async with httpx.AsyncClient(timeout=self.gpu.timeout) as client:
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
                        f"[{job_id}] Sending transcription request to worker",
                        extra={"request_id": request_id, "job_id": job_id},
                    )

                    response = await client.post(
                        f"{self.base_url}/transcribe",
                        files=files,
                        data=data,
                        headers=headers,
                    )

                if response.status_code == 200:
                    result = response.json()
                    log.info(
                        f"[{job_id}] Worker transcription succeeded",
                        extra={"request_id": request_id, "job_id": job_id},
                    )
                    return TranscriptionResult(
                        success=True,
                        segments=result.get("segments"),
                        formatted=result.get("formatted"),
                        stats=result.get("stats"),
                    )
                else:
                    log.error(
                        f"[{job_id}] Worker transcription failed with status {response.status_code}",
                        extra={
                            "request_id": request_id,
                            "job_id": job_id,
                            "status_code": response.status_code,
                        },
                    )
                    return TranscriptionResult(
                        success=False,
                        error=f"GPU worker returned {response.status_code}: {response.text}",
                    )

        except httpx.TimeoutException:
            log.error(
                f"[{job_id}] Worker timeout",
                extra={"request_id": request_id, "job_id": job_id},
            )
            return TranscriptionResult(success=False, error="GPU worker timeout")
        except Exception as e:
            log.error(
                f"[{job_id}] Worker request error: {e}",
                extra={"request_id": request_id, "job_id": job_id},
            )
            return TranscriptionResult(success=False, error=str(e))
