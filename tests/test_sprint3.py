"""Sprint 3 tests — DB migrations, persistent JobStore, error classification."""

from datetime import datetime

import pytest
from sqlalchemy import text

from backend.app.database import Database

# --- Database Migration Tests ---


class TestDatabaseMigrations:
    """Test versioned migration system."""

    @pytest.mark.asyncio
    async def test_fresh_db_gets_latest_version(self, tmp_path):
        """Fresh database should have schema version = max migration."""
        db = Database(tmp_path / "fresh.db")
        await db.connect()

        async with db.engine.begin() as conn:
            result = await conn.execute(text("SELECT version FROM _schema_version"))
            version = result.fetchone()[0]

        assert version == 2  # Latest migration
        await db.close()

    @pytest.mark.asyncio
    async def test_migration_is_idempotent(self, tmp_path):
        """Running connect() twice should not fail."""
        db = Database(tmp_path / "idem.db")
        await db.connect()
        await db.connect()  # Should not raise
        await db.close()

    @pytest.mark.asyncio
    async def test_jobs_table_exists(self, tmp_path):
        """After migrations, jobs table should exist."""
        db = Database(tmp_path / "jobs.db")
        await db.connect()

        async with db.engine.begin() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
            )
            assert result.fetchone() is not None

        await db.close()


# --- Persistent JobStore Tests ---


class TestPersistentJobStore:
    """Test that JobStore survives reconnection."""

    @pytest.mark.asyncio
    async def test_job_survives_reconnect(self, tmp_path):
        """Job created before disconnect should be available after reconnect."""
        db_path = tmp_path / "persist.db"

        # Create job
        db1 = Database(db_path)
        await db1.connect()

        from backend.app.repositories.meeting_repository import MeetingRepository
        from backend.app.services.job_store import JobStore

        repo = MeetingRepository(db1)
        mid = await repo.create(title="Test", date=datetime.now())

        store1 = JobStore(db1)
        await store1.create_job("persist-1", meeting_id=mid)
        await store1.update_status("persist-1", "completed")
        await db1.close()

        # Reconnect and verify
        db2 = Database(db_path)
        await db2.connect()
        store2 = JobStore(db2)

        job = await store2.get_job("persist-1")
        assert job is not None
        assert job["status"] == "completed"
        await db2.close()


# --- Error Classification Tests ---


class TestErrorClassification:
    """Test GPU worker error classes."""

    @pytest.fixture(autouse=True)
    def _add_gpu_worker_path(self):
        import sys

        sys.path.insert(0, "gpu-worker")
        yield
        sys.path.pop(0)

    def test_audio_error_is_pipeline_error(self):
        from core.errors import AudioError, PipelineError

        err = AudioError("ffmpeg failed")
        assert isinstance(err, PipelineError)

    def test_timeout_error_is_pipeline_error(self):
        from core.errors import PipelineError, TranscriptionTimeoutError

        err = TranscriptionTimeoutError("timed out")
        assert isinstance(err, PipelineError)

    def test_model_error_is_pipeline_error(self):
        from core.errors import ModelError, PipelineError

        err = ModelError("model crash")
        assert isinstance(err, PipelineError)
