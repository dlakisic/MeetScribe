"""Unified transcription service with GPU, wake-up, and fallback support."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..core.logging import get_logger
from ..interfaces import AbstractTranscriber
from .result import TranscriptionResult

if TYPE_CHECKING:
    from .fallback import FallbackTranscriber
    from .gpu_client import GPUClient
    from .gpu_waker import GPUWaker

log = get_logger("transcription")


class TranscriptionService(AbstractTranscriber):
    """Orchestrates transcription via GPU worker, with optional wake-up and CPU fallback.

    Dependencies are injected — this class no longer creates its own.
    """

    def __init__(
        self,
        gpu_client: GPUClient,
        fallback: FallbackTranscriber | None = None,
        gpu_waker: GPUWaker | None = None,
    ):
        self.gpu_client = gpu_client
        self.fallback = fallback
        self.gpu_waker = gpu_waker

    async def transcribe(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
        job_id: str,
    ) -> TranscriptionResult:
        """Transcribe meeting using GPU or fallback to CPU."""
        request_id = metadata.get("request_id")
        gpu_available = await self.gpu_client.is_gpu_available()

        if not gpu_available and self.gpu_waker:
            gpu_available = await self.gpu_waker.try_wake(job_id)

        if gpu_available:
            log.info(
                f"[{job_id}] Using GPU worker at {self.gpu_client.base_url}",
                extra={"request_id": request_id, "job_id": job_id},
            )
            result = await self.gpu_client.transcribe(mic_path, tab_path, metadata)
            if result.success:
                return result
            log.error(
                f"[{job_id}] GPU transcription failed: {result.error}",
                extra={"request_id": request_id, "job_id": job_id},
            )

        if self.fallback:
            log.info(
                f"[{job_id}] GPU unavailable, using CPU fallback",
                extra={"request_id": request_id, "job_id": job_id},
            )
            return await self.fallback.transcribe(mic_path, tab_path, metadata)

        return TranscriptionResult(
            success=False,
            error="GPU unavailable and fallback disabled",
        )

    async def is_gpu_available(self) -> bool:
        """Check if the GPU worker is reachable."""
        return await self.gpu_client.is_gpu_available()
