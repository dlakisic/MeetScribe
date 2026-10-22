"""Schemas for RAG API."""

from datetime import datetime

from pydantic import BaseModel, Field


class RAGAskRequest(BaseModel):
    query: str = Field(..., min_length=3, description="User question")
    meeting_ids: list[int] | None = Field(default=None, description="Optional meeting scope")
    top_k: int = Field(default=5, ge=1, le=20)


class RAGCitation(BaseModel):
    meeting_id: int
    segment_id: int
    speaker: str
    text: str
    start_time: float
    end_time: float
    score: float
    segment_ids: list[int] = Field(default_factory=list)
    meeting_title: str | None = None
    meeting_date: datetime | None = None


class RAGAskResponse(BaseModel):
    answer: str
    confidence: float
    citations: list[RAGCitation]
