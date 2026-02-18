"""Optional Langfuse observability for LLM extraction."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .logging import get_logger

log = get_logger("llm_observability")


@dataclass
class ExtractionSpan:
    """In-memory extraction span for telemetry and logging."""

    context: dict[str, Any]
    started_at: float
    trace: Any | None = None
    generation: Any | None = None


class LLMObservability:
    """Wrapper that emits Langfuse spans when configured, no-ops otherwise."""

    def __init__(self):
        self.prompt_version = os.getenv("MEETSCRIBE_EXTRACTION_PROMPT_VERSION", "v1")
        self.capture_input = (
            os.getenv("MEETSCRIBE_LANGFUSE_CAPTURE_INPUT", "false").lower() == "true"
        )
        self.capture_output = (
            os.getenv("MEETSCRIBE_LANGFUSE_CAPTURE_OUTPUT", "false").lower() == "true"
        )
        self.client = self._build_client()

    def _build_client(self) -> Any | None:
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except Exception:
            log.debug("Langfuse SDK not installed; LLM telemetry disabled")
            return None

        public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
        if not public_key or not secret_key:
            return None

        host = os.getenv("LANGFUSE_HOST")
        kwargs = {"public_key": public_key, "secret_key": secret_key}
        if host:
            kwargs["host"] = host

        try:
            return Langfuse(**kwargs)
        except Exception as exc:
            log.warning("Failed to initialize Langfuse client", extra={"error": str(exc)})
            return None

    def start_extraction(self, context: dict[str, Any], transcript_text: str) -> ExtractionSpan:
        """Create an extraction span and optional Langfuse trace/generation."""
        ctx = dict(context)
        ctx.setdefault("feature", "extraction")
        ctx.setdefault("prompt_version", self.prompt_version)

        transcript_hash = sha256(transcript_text.encode("utf-8")).hexdigest()[:16]
        metadata = {
            **ctx,
            "transcript_length": len(transcript_text),
            "transcript_sha16": transcript_hash,
        }

        trace = None
        generation = None

        if self.client:
            try:
                trace = self.client.trace(
                    name="meeting_extraction",
                    session_id=str(ctx.get("meeting_id", "unknown")),
                    metadata=metadata,
                )
                generation_input = transcript_text if self.capture_input else None
                generation = trace.generation(
                    name="llm_extraction",
                    model=str(ctx.get("model", "unknown")),
                    metadata={
                        "feature": ctx["feature"],
                        "prompt_version": ctx["prompt_version"],
                    },
                    input=generation_input,
                )
            except Exception as exc:
                log.warning("Failed to start Langfuse span", extra={"error": str(exc)})
                trace = None
                generation = None

        return ExtractionSpan(
            context=ctx, started_at=time.monotonic(), trace=trace, generation=generation
        )

    def finish_success(self, span: ExtractionSpan, output: dict[str, Any]) -> None:
        """Finalize successful extraction span."""
        duration_ms = round((time.monotonic() - span.started_at) * 1000, 1)
        if span.generation:
            try:
                generation_output = output if self.capture_output else {"captured": False}
                span.generation.end(output=generation_output, metadata={"duration_ms": duration_ms})
            except Exception as exc:
                log.warning("Failed to end Langfuse generation", extra={"error": str(exc)})

        log.info(
            "LLM extraction success",
            extra={
                "meeting_id": span.context.get("meeting_id"),
                "job_id": span.context.get("job_id"),
                "request_id": span.context.get("request_id"),
                "prompt_version": span.context.get("prompt_version"),
                "duration_ms": duration_ms,
            },
        )

    def finish_error(self, span: ExtractionSpan, error: Exception) -> None:
        """Finalize failed extraction span."""
        duration_ms = round((time.monotonic() - span.started_at) * 1000, 1)
        if span.generation:
            try:
                span.generation.end(
                    level="ERROR",
                    status_message=str(error),
                    metadata={"duration_ms": duration_ms},
                )
            except Exception as exc:
                log.warning("Failed to end Langfuse error span", extra={"error": str(exc)})

        log.warning(
            "LLM extraction failed",
            extra={
                "meeting_id": span.context.get("meeting_id"),
                "job_id": span.context.get("job_id"),
                "request_id": span.context.get("request_id"),
                "prompt_version": span.context.get("prompt_version"),
                "duration_ms": duration_ms,
                "error": str(error),
            },
        )
