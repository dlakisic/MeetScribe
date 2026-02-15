"""Shared test fixtures for MeetScribe."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import Config
from backend.app.database import Database
from backend.app.repositories.meeting_repository import MeetingRepository
from backend.app.services.job_store import JobStore
from backend.app.services.meeting_service import MeetingService

# --- Database fixtures ---


@pytest.fixture
async def test_db(tmp_path):
    """In-memory SQLite database for testing."""
    db = Database(tmp_path / "test.db")
    await db.connect()
    yield db
    await db.close()


@pytest.fixture
def test_repo(test_db):
    """Repository backed by test database."""
    return MeetingRepository(test_db)


@pytest.fixture
async def seed_meeting(test_repo):
    """Insert a meeting with transcript and segments, return IDs."""
    meeting_id = await test_repo.create(
        title="Test Meeting",
        date=datetime(2026, 1, 15, 10, 0),
        platform="Zoom",
        duration=1800.0,
    )

    segments = [
        {"speaker": "Alice", "text": "Hello everyone", "start": 0.0, "end": 5.0},
        {"speaker": "Bob", "text": "Hi Alice", "start": 5.0, "end": 8.0},
    ]
    await test_repo.save_transcript(
        meeting_id=meeting_id,
        segments=segments,
        formatted="[0:00] Alice: Hello everyone\n[0:05] Bob: Hi Alice",
        stats={"duration": 8.0, "speakers": 2},
    )

    return {"meeting_id": meeting_id}


# --- App fixtures for route testing ---


@pytest.fixture
def test_config(tmp_path):
    """Test config with no auth and temp dirs."""
    config = Config(
        data_dir=tmp_path / "data",
        upload_dir=tmp_path / "uploads",
        db_path=tmp_path / "test.db",
        api_token=None,
    )
    return config


@pytest.fixture
async def test_app(test_config):
    """FastAPI app wired with test database and mock services."""
    from backend.app.main import app

    db = Database(test_config.db_path)
    await db.connect()

    repo = MeetingRepository(db)
    job_store = JobStore()
    mock_transcriber = AsyncMock()
    mock_extraction = AsyncMock()

    service = MeetingService(repo, mock_transcriber, job_store, mock_extraction)

    app.state.config = test_config
    app.state.db = db
    app.state.meeting_service = service
    app.state.job_store = job_store

    yield app

    await db.close()


@pytest.fixture
async def client(test_app):
    """Async HTTP client for testing routes."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
