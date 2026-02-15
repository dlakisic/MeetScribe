from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    success: bool
    segments: list[dict] | None = None
    formatted: str | None = None
    stats: dict | None = None
    error: str | None = None
    used_fallback: bool = False
