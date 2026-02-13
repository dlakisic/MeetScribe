from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Relationship, JSON, Column

class MeetingBase(SQLModel):
    title: str
    date: datetime
    duration: Optional[float] = None
    platform: Optional[str] = None
    url: Optional[str] = None
    status: str = Field(default="processing")

class Meeting(MeetingBase, table=True):
    __tablename__ = "meetings"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    transcript: Optional["Transcript"] = Relationship(back_populates="meeting")
    segments: List["Segment"] = Relationship(back_populates="meeting")

class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id", unique=True)
    full_text: str
    formatted: Optional[str] = None
    summary: Optional[str] = None
    stats: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.now)

    meeting: Meeting = Relationship(back_populates="transcript")

class Segment(SQLModel, table=True):
    __tablename__ = "segments"  # type: ignore

    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_id: int = Field(foreign_key="meetings.id")
    speaker: str
    text: str
    start_time: float
    end_time: float
    confidence: Optional[float] = None

    meeting: Meeting = Relationship(back_populates="segments")
