"""Interface contract tests."""

from backend.app.interfaces import (
    AbstractExtractionService,
    AbstractJobStore,
    AbstractMeetingRepository,
    AbstractTranscriber,
)
from backend.app.repositories.meeting_repository import MeetingRepository
from backend.app.services.extraction_service import ExtractionService
from backend.app.services.job_store import JobStore
from backend.app.transcription.service import TranscriptionService


def test_repo_implements_abc():
    assert issubclass(MeetingRepository, AbstractMeetingRepository)


def test_transcription_service_implements_abc():
    assert issubclass(TranscriptionService, AbstractTranscriber)


def test_extraction_service_implements_abc():
    assert issubclass(ExtractionService, AbstractExtractionService)


def test_job_store_implements_abc():
    assert issubclass(JobStore, AbstractJobStore)
