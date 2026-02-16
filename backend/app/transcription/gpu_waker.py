"""GPU wake-up logic via smart plug with health polling."""

import asyncio

from ..core.logging import get_logger

log = get_logger("gpu_waker")


class GPUWaker:
    """Responsible for waking the GPU PC via smart plug and waiting for it to boot."""

    def __init__(self, smart_plug, gpu_client, boot_wait_time: int, check_interval: int = 10):
        self.smart_plug = smart_plug
        self.gpu_client = gpu_client
        self.boot_wait_time = boot_wait_time
        self.check_interval = check_interval

    async def try_wake(self, job_id: str) -> bool:
        """Turn on the smart plug and poll GPU health until ready or timeout."""
        if not self.smart_plug.is_configured():
            return False

        log.info(f"[{job_id}] GPU not available, powering on via smart plug")

        if not await self.smart_plug.turn_on():
            log.error(f"[{job_id}] Failed to turn on smart plug")
            return False

        log.info(f"[{job_id}] Smart plug ON, waiting for GPU PC to boot")

        elapsed = 0
        while elapsed < self.boot_wait_time:
            await asyncio.sleep(self.check_interval)
            elapsed += self.check_interval
            log.debug(f"[{job_id}] Waiting for GPU ({elapsed}/{self.boot_wait_time}s)")

            if await self.gpu_client.is_gpu_available():
                log.info(f"[{job_id}] GPU worker is now available")
                return True

        log.warning(f"[{job_id}] GPU did not become available after {self.boot_wait_time}s")
        return False
