"""Unified transcription service with GPU, smart plug, and fallback support."""

import asyncio
from pathlib import Path

from ..config import Config
from ..core.logging import get_logger
from .fallback import FallbackTranscriber
from .gpu_client import GPUClient
from .result import TranscriptionResult

log = get_logger("transcription")


class TranscriptionService:
    """Orchestrates transcription via GPU worker, with smart plug wake-up and CPU fallback."""

    def __init__(self, config: Config):
        self.config = config
        self.gpu_client = GPUClient(config)
        self.fallback = FallbackTranscriber(config) if config.fallback.enabled else None
        self.smart_plug = None

        if config.smart_plug.enabled:
            from ..smart_plug import SmartPlug

            self.smart_plug = SmartPlug(config.smart_plug)
            log.info(f"SmartPlug configured for device {config.smart_plug.device_id}")

    async def transcribe(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
        job_id: str,
    ) -> TranscriptionResult:
        """Transcribe meeting using GPU or fallback to CPU."""
        gpu_available = await self.gpu_client.is_gpu_available()

        if not gpu_available and self.smart_plug:
            gpu_available = await self._try_wake_gpu(job_id)

        if gpu_available:
            log.info(
                f"[{job_id}] Using GPU worker at {self.config.gpu.host}:{self.config.gpu.worker_port}"
            )
            result = await self.gpu_client.transcribe(mic_path, tab_path, metadata)
            if result.success:
                return result
            log.error(f"[{job_id}] GPU transcription failed: {result.error}")

        if self.fallback:
            log.info(f"[{job_id}] GPU unavailable, using CPU fallback")
            return await self.fallback.transcribe(mic_path, tab_path, metadata)

        return TranscriptionResult(
            success=False,
            error="GPU unavailable and fallback disabled",
        )

    async def _try_wake_gpu(self, job_id: str) -> bool:
        """Try to wake up the GPU PC via smart plug."""
        if not self.smart_plug or not self.smart_plug.is_configured():
            return False

        log.info(f"[{job_id}] GPU not available, powering on via smart plug")

        if not await self.smart_plug.turn_on():
            log.error(f"[{job_id}] Failed to turn on smart plug")
            return False

        log.info(f"[{job_id}] Smart plug ON, waiting for GPU PC to boot")

        boot_time = self.config.smart_plug.boot_wait_time
        check_interval = 10
        elapsed = 0

        while elapsed < boot_time:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            log.debug(f"[{job_id}] Waiting for GPU ({elapsed}/{boot_time}s)")

            if await self.gpu_client.is_gpu_available():
                log.info(f"[{job_id}] GPU worker is now available")
                return True

        log.warning(f"[{job_id}] GPU did not become available after {boot_time}s")
        return False
