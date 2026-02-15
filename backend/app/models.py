from datetime import datetime
from typing import Any, Optional

from sqlmodel import JSON, Column, Field, Relationship, SQLModel


class MeetingBase(SQLModel):
    title: str
    date: datetime
    duration: float | None = None
    platform: str | None = None
    url: str | None = None
    status: str = Field(default="processing")


class Meeting(MeetingBase, table=True):
    __tablename__ = "meetings"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    transcript: Optional["Transcript"] = Relationship(back_populates="meeting")
    segments: list["Segment"] = Relationship(back_populates="meeting")

    extracted_data: dict[str, Any] = Field(default={}, sa_column=Column(JSON))


class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", unique=True)
    full_text: str
    formatted: str | None = None
    summary: str | None = None
    stats: dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)

    meeting: Optional["Meeting"] = Relationship(back_populates="transcript")


class Segment(SQLModel, table=True):
    __tablename__ = "segments"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id")
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: float | None = None

    meeting: Optional["Meeting"] = Relationship(back_populates="segments")
