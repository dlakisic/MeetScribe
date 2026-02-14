"""Client for communicating with the GPU worker via HTTP."""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Config


@dataclass
class TranscriptionResult:
    success: bool
    segments: list[dict] | None = None
    formatted: str | None = None
    stats: dict | None = None
    error: str | None = None
    used_fallback: bool = False


class GPUClient:
    """HTTP client for the remote GPU transcription worker."""

    def __init__(self, config: Config):
        self.config = config
        self.gpu = config.gpu
        self.base_url = f"http://{self.gpu.host}:{self.gpu.worker_port}"

    async def is_gpu_available(self) -> bool:
        """Check if the GPU worker is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("status") == "ok"
                return False
        except Exception:
            return False

    async def transcribe(
        self,
        mic_path: Path,
        tab_path: Path,
        metadata: dict,
    ) -> TranscriptionResult:
        """Send files to GPU worker and get transcription result."""
        try:
            async with httpx.AsyncClient(timeout=self.gpu.timeout) as client:
                # Prepare multipart form data
                files = {
                    "mic_file": (mic_path.name, open(mic_path, "rb"), "audio/webm"),
                    "tab_file": (tab_path.name, open(tab_path, "rb"), "audio/webm"),
                }
                data = {
                    "metadata": json.dumps(metadata),
                }

                response = await client.post(
                    f"{self.base_url}/transcribe",
                    files=files,
                    data=data,
                )

                # Close file handles
                for _, (_, f, _) in files.items():
                    f.close()

                if response.status_code == 200:
                    result = response.json()
                    return TranscriptionResult(
                        success=True,
                        segments=result.get("segments"),
                        formatted=result.get("formatted"),
                        stats=result.get("stats"),
                    )
                else:
                    return TranscriptionResult(
                        success=False,
                        error=f"GPU worker returned {response.status_code}: {response.text}",
                    )

        except httpx.TimeoutException:
            return TranscriptionResult(
                success=False,
                error="GPU worker timeout",
            )
        except Exception as e:
            return TranscriptionResult(
                success=False,
                error=str(e),
            )


class FallbackTranscriber:
    """CPU fallback transcriber for when GPU is unavailable."""

    def __init__(self, config: Config):
        self.config = config

    async def transcribe(
        self,
        mic_path: Path,
        tab_path: Path,
        metadata: dict,
    ) -> TranscriptionResult:
        """Run transcription locally on CPU."""
        # Import here to avoid loading the model unless needed
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "gpu-worker"))

        try:
            from transcribe import process_meeting

            output_path = mic_path.parent / "output.json"

            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: process_meeting(
                    mic_path=mic_path,
                    tab_path=tab_path,
                    metadata=metadata,
                    output_path=output_path,
                    model_size=self.config.fallback.model_size,
                    device="cpu",
                ),
            )

            return TranscriptionResult(
                success=True,
                segments=result.get("segments"),
                formatted=result.get("formatted"),
                stats=result.get("stats"),
                used_fallback=True,
            )
        except Exception as e:
            return TranscriptionResult(
                success=False,
                error=str(e),
                used_fallback=True,
            )


class TranscriptionService:
    """Unified transcription service with GPU, smart plug, and fallback support."""

    def __init__(self, config: Config):
        self.config = config
        self.gpu_client = GPUClient(config)
        self.fallback = FallbackTranscriber(config) if config.fallback.enabled else None
        self.smart_plug = None

        # Initialize smart plug if configured
        if config.smart_plug.enabled:
            from .smart_plug import SmartPlug

            self.smart_plug = SmartPlug(config.smart_plug)
            print(f"[SmartPlug] Configured for device {config.smart_plug.device_id}")

    async def _try_wake_gpu(self, job_id: str) -> bool:
        """Try to wake up the GPU PC via smart plug."""
        if not self.smart_plug or not self.smart_plug.is_configured():
            return False

        print(f"[{job_id}] GPU not available, attempting to power on via smart plug...")

        # Turn on the plug
        if not await self.smart_plug.turn_on():
            print(f"[{job_id}] Failed to turn on smart plug")
            return False

        print(f"[{job_id}] Smart plug turned ON, waiting for GPU PC to boot...")

        # Wait for PC to boot and worker to start
        boot_time = self.config.smart_plug.boot_wait_time
        check_interval = 10  # Check every 10 seconds
        elapsed = 0

        while elapsed < boot_time:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            print(f"[{job_id}] Waiting for GPU... ({elapsed}/{boot_time}s)")

            if await self.gpu_client.is_gpu_available():
                print(f"[{job_id}] GPU worker is now available!")
                return True

        print(f"[{job_id}] GPU did not become available after {boot_time}s")
        return False

    async def transcribe(
        self,
        mic_path: Path,
        tab_path: Path,
        metadata: dict,
        job_id: str,
    ) -> TranscriptionResult:
        """Transcribe meeting using GPU or fallback to CPU."""
        # Try GPU first
        gpu_available = await self.gpu_client.is_gpu_available()

        # If GPU not available, try to wake it up
        if not gpu_available and self.smart_plug:
            gpu_available = await self._try_wake_gpu(job_id)

        if gpu_available:
            print(
                f"[{job_id}] Using GPU worker at {self.config.gpu.host}:{self.config.gpu.worker_port}"
            )
            result = await self.gpu_client.transcribe(mic_path, tab_path, metadata)
            if result.success:
                return result
            print(f"[{job_id}] GPU transcription failed: {result.error}")

        # Fallback to CPU
        if self.fallback:
            print(f"[{job_id}] GPU unavailable, using CPU fallback")
            return await self.fallback.transcribe(mic_path, tab_path, metadata)

        return TranscriptionResult(
            success=False,
            error="GPU unavailable and fallback disabled",
        )
