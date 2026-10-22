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

    assert version == 5
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


@pytest.mark.asyncio
async def test_fts_migration_indexes_existing_segments(tmp_path):
    """Upgrading a v2 database must index segments written before the FTS table existed."""
    db = Database(tmp_path / "upgrade.db")
    await db.connect()
    async with db.engine.begin() as conn:
        for name in ("segments_fts_ai", "segments_fts_ad", "segments_fts_au"):
            await conn.execute(text(f"DROP TRIGGER {name}"))
        await conn.execute(text("DROP TABLE segments_fts"))
        await conn.execute(text("UPDATE _schema_version SET version = 2"))
        await conn.execute(
            text(
                "INSERT INTO meetings (title, date, status, created_at, updated_at)"
                " VALUES ('Old', '2025-01-01', 'done', '2025-01-01', '2025-01-01')"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO segments (meeting_id, speaker, text, start_time, end_time)"
                " VALUES (1, 'Alice', 'Ancien budget', 0, 1)"
            )
        )

    await db.connect()

    async with db.engine.begin() as conn:
        result = await conn.execute(
            text("SELECT rowid FROM segments_fts WHERE segments_fts MATCH 'budget'")
        )
        assert result.fetchone() is not None
    await db.close()
