"""Abstract base classes for dependency inversion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transcription.result import TranscriptionResult


class AbstractMeetingRepository(ABC):
    """Interface for meeting data access."""

    @abstractmethod
    async def create(
        self,
        title: str,
        date: datetime,
        platform: str | None = None,
        url: str | None = None,
        duration: float | None = None,
        audio_file: str | None = None,
    ) -> int: ...

    @abstractmethod
    async def get(self, meeting_id: int) -> dict | None: ...

    @abstractmethod
    async def list(self, limit: int = 50, offset: int = 0) -> list[dict]: ...

    @abstractmethod
    async def delete(self, meeting_id: int) -> bool: ...

    @abstractmethod
    async def update_fields(self, meeting_id: int, fields: dict) -> bool: ...

    @abstractmethod
    async def update_status(self, meeting_id: int, status: str) -> None: ...

    @abstractmethod
    async def save_transcript(
        self,
        meeting_id: int,
        segments: list[dict],
        formatted: str,
        stats: dict,
    ) -> None: ...

    @abstractmethod
    async def get_transcript(self, meeting_id: int) -> dict | None: ...

    @abstractmethod
    async def save_extracted_data(self, meeting_id: int, data: dict) -> None: ...

    @abstractmethod
    async def update_segment_text(self, segment_id: int, text: str) -> bool: ...

    @abstractmethod
    async def update_speaker(self, meeting_id: int, old_name: str, new_name: str) -> int: ...


class AbstractTranscriber(ABC):
    """Interface for transcription services."""

    @abstractmethod
    async def transcribe(
        self,
        mic_path: Path | None,
        tab_path: Path | None,
        metadata: dict,
        job_id: str,
    ) -> TranscriptionResult: ...

    @abstractmethod
    async def is_gpu_available(self) -> bool: ...


class AbstractExtractionService(ABC):
    """Interface for LLM-based extraction."""

    @abstractmethod
    async def extract_from_transcript(self, text: str): ...


class AbstractJobStore(ABC):
    """Interface for job status tracking."""

    @abstractmethod
    async def create_job(self, job_id: str, meeting_id: int) -> None: ...

    @abstractmethod
    async def update_status(
        self,
        job_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None: ...

    @abstractmethod
    async def get_job(self, job_id: str) -> dict | None: ...
