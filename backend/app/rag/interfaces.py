"""Interfaces for modular RAG components."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RAGChunk:
    meeting_id: int
    segment_id: int
    speaker: str
    text: str
    start_time: float
    end_time: float
    score: float = 0.0
    # All segments covered by the chunk (a window of consecutive turns).
    segment_ids: list[int] = field(default_factory=list)
    meeting_title: str | None = None
    meeting_date: datetime | None = None


@dataclass
class RAGAnswer:
    answer: str
    citations: list[RAGChunk]
    confidence: float
    # True when the LLM was unavailable and an extractive answer was returned.
    fallback_used: bool = False


class AbstractRetriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query: str,
        meeting_ids: list[int] | None = None,
        top_k: int = 5,
    ) -> list[RAGChunk]: ...


class AbstractReranker(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RAGChunk],
        top_k: int = 5,
    ) -> list[RAGChunk]: ...


class AbstractAnswerSynthesizer(ABC):
    @abstractmethod
    async def synthesize(
        self,
        query: str,
        citations: list[RAGChunk],
    ) -> RAGAnswer: ...
