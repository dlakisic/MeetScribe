"""CPU fallback transcriber using the gpu-worker pipeline.

Requires the gpu-worker code to be importable. The worker_path config
(or MEETSCRIBE_FALLBACK_WORKER_PATH env var) should point to the
gpu-worker/ directory. Defaults to auto-detection relative to the project root.
"""

import asyncio
import sys
from pathlib import Path

from ..config import Config
from ..core.logging import get_logger
from .result import TranscriptionResult

log = get_logger("fallback")


def _resolve_worker_path(config: Config) -> str:
    """Resolve the gpu-worker path from config or auto-detect."""
    if config.fallback.worker_path:
        return config.fallback.worker_path
    return str(Path(__file__).parent.parent.parent.parent / "gpu-worker")


class FallbackTranscriber:
    """CPU fallback transcriber for when GPU is unavailable."""

    def __init__(self, config: Config):
        self.config = config
        self._worker_path = _resolve_worker_path(config)

    async def transcribe(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
    ) -> TranscriptionResult:
        """Run transcription locally on CPU."""
        try:
            if self._worker_path not in sys.path:
                sys.path.insert(0, self._worker_path)

            from transcribe import process_meeting

            base_path = mic_path or tab_path
            output_path = base_path.parent / "output.json"

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
        except ImportError:
            log.error(
                f"Fallback unavailable: gpu-worker not found at {self._worker_path}. "
                "Set MEETSCRIBE_FALLBACK_WORKER_PATH or check your deployment."
            )
            return TranscriptionResult(
                success=False,
                error="Fallback transcriber not available (gpu-worker not importable)",
                used_fallback=True,
            )
        except Exception as e:
            return TranscriptionResult(
                success=False,
                error=str(e),
                used_fallback=True,
            )
