"""SQLite database for storing meetings and transcripts."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        # Use aiosqlite driver
        self.database_url = f"sqlite+aiosqlite:///{db_path}"
        self.engine = create_async_engine(self.database_url, echo=False)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    async def connect(self):
        """Create tables if they don't exist, then run migrations."""
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        await self._migrate()

    async def _migrate(self):
        """Run lightweight schema migrations for existing databases."""
        async with self.engine.begin() as conn:
            # Get existing columns on meetings table
            result = await conn.execute(text("PRAGMA table_info(meetings)"))
            columns = {row[1] for row in result.fetchall()}

            if "audio_file" not in columns:
                await conn.execute(
                    text("ALTER TABLE meetings ADD COLUMN audio_file TEXT")
                )

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()

    def session(self) -> AsyncSession:
        """Get a new async session."""
        return self.async_session()
