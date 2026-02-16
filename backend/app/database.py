"""SQLite database with versioned migrations."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from .core.logging import get_logger

log = get_logger("database")

# Ordered migrations: (version, description, sql_statements)
# For fresh DBs, create_all handles the schema; migrations only run for upgrades.
MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "Add audio_file column to meetings",
        ["ALTER TABLE meetings ADD COLUMN audio_file TEXT"],
    ),
    (
        2,
        "Create jobs table",
        [
            "CREATE TABLE IF NOT EXISTS jobs ("
            "  id INTEGER PRIMARY KEY,"
            "  job_id TEXT NOT NULL UNIQUE,"
            "  meeting_id INTEGER NOT NULL REFERENCES meetings(id),"
            "  status TEXT NOT NULL DEFAULT 'queued',"
            "  created_at TIMESTAMP,"
            "  updated_at TIMESTAMP,"
            "  result JSON,"
            "  error TEXT"
            ")",
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_job_id ON jobs(job_id)",
        ],
    ),
]


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.database_url = f"sqlite+aiosqlite:///{db_path}"
        self.engine = create_async_engine(self.database_url, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def connect(self):
        """Create tables if they don't exist, then run pending migrations."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        await self._ensure_version_table()
        await self._run_migrations()

    async def _ensure_version_table(self):
        """Create _schema_version table if it doesn't exist."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS _schema_version "
                    "(id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL)"
                )
            )
            result = await conn.execute(text("SELECT version FROM _schema_version"))
            if result.fetchone() is None:
                await conn.execute(text("INSERT INTO _schema_version (id, version) VALUES (1, 0)"))

    async def _run_migrations(self):
        """Run all pending migrations in order."""
        async with self.engine.begin() as conn:
            result = await conn.execute(text("SELECT version FROM _schema_version"))
            current = result.fetchone()[0]

            for version, description, statements in MIGRATIONS:
                if version <= current:
                    continue

                log.info(f"Running migration v{version}: {description}")
                for sql in statements:
                    try:
                        await conn.execute(text(sql))
                    except Exception as e:
                        if "duplicate column" in str(e).lower():
                            log.debug(f"  Skipped (already applied): {sql[:60]}")
                        else:
                            raise

                await conn.execute(
                    text("UPDATE _schema_version SET version = :v"),
                    {"v": version},
                )
                log.info(f"Migration v{version} complete")

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        """Get a new async session."""
        return self.async_session()
