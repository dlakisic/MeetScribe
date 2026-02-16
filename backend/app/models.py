from datetime import datetime
from typing import Any

from sqlmodel import JSON, Column, Field, Relationship, SQLModel


class MeetingBase(SQLModel):
    title: str
    date: datetime
    duration: float | None = None
    platform: str | None = None
    url: str | None = None
    status: str = Field(default="processing")
    audio_file: str | None = None  # Relative path to audio file in upload_dir


class Meeting(MeetingBase, table=True):
    __tablename__ = "meetings"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    transcript: Transcript = Relationship(
        back_populates="meeting",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    segments: list[Segment] = Relationship(
        back_populates="meeting",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )

    extracted_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", unique=True)
    full_text: str
    formatted: str | None = None
    summary: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)

    meeting: Meeting | None = Relationship(back_populates="transcript")


class Job(SQLModel, table=True):
    __tablename__ = "jobs"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    job_id: str = Field(unique=True, index=True)
    meeting_id: int = Field(foreign_key="meetings.id")
    status: str = Field(default="queued")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    error: str | None = None


class Segment(SQLModel, table=True):
    __tablename__ = "segments"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id")
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: float | None = None

    meeting: Meeting | None = Relationship(back_populates="segments")
