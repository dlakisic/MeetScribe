"""Database migration tests."""

import pytest
from sqlalchemy import text

from backend.app.database import Database


@pytest.mark.asyncio
async def test_fresh_db_gets_latest_version(tmp_path):
    """Fresh database should have schema version equal to latest migration."""
    db = Database(tmp_path / "fresh.db")
    await db.connect()

    async with db.engine.begin() as conn:
        result = await conn.execute(text("SELECT version FROM _schema_version"))
        version = result.fetchone()[0]

    assert version == 2
    await db.close()


@pytest.mark.asyncio
async def test_migration_is_idempotent(tmp_path):
    """Running connect() twice should not fail."""
    db = Database(tmp_path / "idem.db")
    await db.connect()
    await db.connect()
    await db.close()


@pytest.mark.asyncio
async def test_jobs_table_exists(tmp_path):
    """After migrations, jobs table should exist."""
    db = Database(tmp_path / "jobs.db")
    await db.connect()

    async with db.engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        )
        assert result.fetchone() is not None

    await db.close()
