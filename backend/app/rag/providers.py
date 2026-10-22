"""Default public RAG providers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import openai
from instructor.core.exceptions import InstructorError
from pydantic import BaseModel
from sqlalchemy import bindparam, text
from sqlmodel import select

from ..core.llm import LLMFactory
from ..core.logging import get_logger
from ..database import Database
from ..models import Meeting, Segment
from .interfaces import (
    AbstractAnswerSynthesizer,
    AbstractReranker,
    AbstractRetriever,
    RAGAnswer,
    RAGChunk,
)

log = get_logger("rag.providers")

_TOKEN_RE = re.compile(r"\w+")

# Function words that match almost every segment and drown out real signal.
_STOPWORDS_TEXT = """
a an and are as at be but by do does did for from had has have he her his how if in
is it its me my no not of on or our she so that the their them they this to us was we
were what when where which who why will with would you your
au aux avec ce ces cette dans de des du elle en est et il ils je la le les leur lui ma
mais me mes moi mon ne nous on ou par pas pour qu que qui quoi quand comment sa se ses
son sont sur ta te tes toi ton tu un une vos votre vous
"""
_STOPWORDS = frozenset(_STOPWORDS_TEXT.split())


def _fold(text: str) -> str:
    """Lowercase and strip diacritics, matching FTS5's remove_diacritics tokenizer."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokenize(text: str) -> set[str]:
    return {tok for tok in _TOKEN_RE.findall(_fold(text)) if len(tok) > 1 and tok not in _STOPWORDS}


def _stem(term: str) -> str:
    """Crude suffix trimming so prefix queries catch inflections.

    livrer -> livr* (livraison, livré), decide -> deci* (décision), approved -> approv*.
    """
    if len(term) >= 6:
        return term[:-2]
    if len(term) == 5:
        return term[:-1]
    return term


def _query_stems(query: str) -> set[str]:
    return {_stem(term) for term in _tokenize(query)}


@dataclass
class _Window:
    meeting_id: int
    start: float
    end: float
    score: float
    best_segment_id: int
    best_score: float


class KeywordRetriever(AbstractRetriever):
    """Lexical retriever: SQLite FTS5 with BM25 ranking, returning context windows.

    Matching segments are found through the segments_fts index, then hits that
    are close in time are merged into windows of consecutive turns, so an answer
    spread over a question and its reply comes back as one chunk.
    """

    def __init__(
        self,
        db: Database,
        max_hits: int = 200,
        context_seconds: float = 20.0,
        max_window_seconds: float = 120.0,
    ):
        self._db = db
        self._max_hits = max_hits
        self._context_seconds = context_seconds
        self._max_window_seconds = max_window_seconds

    async def retrieve(
        self,
        query: str,
        meeting_ids: list[int] | None = None,
        top_k: int = 5,
    ) -> list[RAGChunk]:
        stems = _query_stems(query)
        if not stems:
            return []

        async with self._db.session() as session:
            hits = await self._search(session, stems, meeting_ids)
            windows = self._merge_windows(hits)[:top_k]
            if not windows:
                return []
            meetings = await self._load_meetings(session, {w.meeting_id for w in windows})
            return [await self._build_chunk(session, w, meetings) for w in windows]

    async def _search(self, session, stems: set[str], meeting_ids: list[int] | None) -> list:
        # Quoting each stem keeps user input from being parsed as FTS5 syntax.
        match = " OR ".join(f'"{stem}"*' for stem in sorted(stems))
        scope = "AND s.meeting_id IN :meeting_ids" if meeting_ids else ""
        # bm25() is lower-is-better; speaker names get half the weight of the text.
        stmt = text(
            "SELECT s.id, s.meeting_id, s.start_time, s.end_time,"
            "       -bm25(segments_fts, 1.0, 0.5) AS score"
            " FROM segments_fts JOIN segments s ON s.id = segments_fts.rowid"
            f" WHERE segments_fts MATCH :match {scope}"
            " ORDER BY score DESC LIMIT :limit"
        )
        params = {"match": match, "limit": self._max_hits}
        if meeting_ids:
            stmt = stmt.bindparams(bindparam("meeting_ids", expanding=True))
            params["meeting_ids"] = meeting_ids
        return (await session.exec(stmt, params=params)).all()

    def _merge_windows(self, hits: list) -> list[_Window]:
        ctx = self._context_seconds
        windows: list[_Window] = []
        for hit in sorted(hits, key=lambda h: (h.meeting_id, h.start_time)):
            start, end = hit.start_time - ctx, hit.end_time + ctx
            last = windows[-1] if windows else None
            if (
                last
                and last.meeting_id == hit.meeting_id
                and start <= last.end
                and end - last.start <= self._max_window_seconds
            ):
                last.end = max(last.end, end)
                last.score += hit.score
                if hit.score > last.best_score:
                    last.best_segment_id, last.best_score = hit.id, hit.score
                continue
            windows.append(_Window(hit.meeting_id, start, end, hit.score, hit.id, hit.score))
        windows.sort(key=lambda w: w.score, reverse=True)
        return windows

    async def _load_meetings(self, session, ids: set[int]) -> dict[int, Meeting]:
        rows = (await session.exec(select(Meeting).where(Meeting.id.in_(ids)))).all()
        return {m.id: m for m in rows}

    async def _build_chunk(self, session, window: _Window, meetings: dict) -> RAGChunk:
        stmt = (
            select(Segment)
            .where(
                Segment.meeting_id == window.meeting_id,
                Segment.end_time >= window.start,
                Segment.start_time <= window.end,
            )
            .order_by(Segment.start_time)
        )
        segments = (await session.exec(stmt)).all()
        best = next(s for s in segments if s.id == window.best_segment_id)
        meeting = meetings.get(window.meeting_id)
        return RAGChunk(
            meeting_id=window.meeting_id,
            segment_id=best.id,
            speaker=best.speaker,
            text="\n".join(f"{s.speaker}: {s.text}" for s in segments),
            start_time=segments[0].start_time,
            end_time=segments[-1].end_time,
            score=round(window.score, 4),
            segment_ids=[s.id for s in segments],
            meeting_title=meeting.title if meeting else None,
            meeting_date=meeting.date if meeting else None,
        )


class IdentityReranker(AbstractReranker):
    """No-op reranker for baseline public mode."""

    async def rerank(
        self, query: str, candidates: list[RAGChunk], top_k: int = 5
    ) -> list[RAGChunk]:
        del query
        return candidates[:top_k]


class CitationSynthesizer(AbstractAnswerSynthesizer):
    """Simple answer builder that prioritizes cited evidence."""

    async def synthesize(
        self,
        query: str,
        citations: list[RAGChunk],
    ) -> RAGAnswer:
        if not citations:
            return RAGAnswer(
                answer=(
                    "Je n'ai pas trouvé de preuve suffisante dans les transcripts pour répondre "
                    "de façon fiable."
                ),
                citations=[],
                confidence=0.0,
            )

        top = citations[0]
        answer = (
            f"Pour la question '{query}', le meilleur extrait indique: \"{top.text}\" "
            f"(speaker: {top.speaker}, t={top.start_time:.1f}-{top.end_time:.1f}s)."
        )

        return RAGAnswer(
            answer=answer, citations=citations, confidence=_query_coverage(query, [top])
        )


def _query_coverage(query: str, chunks: list[RAGChunk]) -> float:
    """Share of the question's terms found in the given excerpts.

    Deterministic and comparable across synthesizers, unlike a confidence
    self-reported by an LLM.
    """
    stems = _query_stems(query)
    if not stems or not chunks:
        return 0.0
    tokens = set().union(*(_tokenize(c.text) for c in chunks))
    covered = [stem for stem in stems if any(tok.startswith(stem) for tok in tokens)]
    return round(len(covered) / len(stems), 3)


class _LLMSynthResponse(BaseModel):
    answer: str
    used_sources: list[int]


class LLMAnswerSynthesizer(AbstractAnswerSynthesizer):
    """LLM-based synthesizer for public RAG answers."""

    def __init__(self):
        self.client = LLMFactory.get_client()
        self.model = LLMFactory.get_model_name()

    async def synthesize(
        self,
        query: str,
        citations: list[RAGChunk],
    ) -> RAGAnswer:
        if not LLMFactory.is_configured():
            raise RuntimeError("RAG synthesizer requires LLM configuration")

        if not citations:
            return RAGAnswer(
                answer="Je n'ai pas trouvé de preuve suffisante dans les transcripts.",
                citations=[],
                confidence=0.0,
            )

        blocks = []
        for number, c in enumerate(citations, start=1):
            date = f" ({c.meeting_date:%Y-%m-%d})" if c.meeting_date else ""
            title = c.meeting_title or f"meeting {c.meeting_id}"
            blocks.append(
                f"[{number}] {title}{date}, t={c.start_time:.1f}-{c.end_time:.1f}s\n{c.text}"
            )
        context = "\n\n".join(blocks)

        resp = await self.client.chat.completions.create(
            model=self.model,
            response_model=_LLMSynthResponse,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You answer only from the numbered meeting excerpts provided. "
                        "Cite the excerpts you rely on inline, like [1] or [2][3]. "
                        "List their numbers in used_sources. If the excerpts don't "
                        "answer the question, say so and leave used_sources empty. "
                        "Answer in the user's language."
                    ),
                },
                {"role": "user", "content": f"Question: {query}\n\nExcerpts:\n{context}"},
            ],
            max_retries=1,
        )

        # Keep only the excerpts the answer actually relies on; ignore invalid numbers.
        used = [
            citations[n - 1] for n in dict.fromkeys(resp.used_sources) if 1 <= n <= len(citations)
        ]
        return RAGAnswer(
            answer=resp.answer, citations=used, confidence=_query_coverage(query, used)
        )


class FallbackSynthesizer(AbstractAnswerSynthesizer):
    """Use the primary synthesizer, falling back when the LLM is missing or failing."""

    def __init__(self, primary: AbstractAnswerSynthesizer, fallback: AbstractAnswerSynthesizer):
        self.primary = primary
        self.fallback = fallback

    async def synthesize(self, query: str, citations: list[RAGChunk]) -> RAGAnswer:
        try:
            return await self.primary.synthesize(query, citations)
        except (RuntimeError, openai.APIError, InstructorError) as exc:
            log.warning("RAG synthesis fell back to extractive mode", extra={"error": str(exc)})
            answer = await self.fallback.synthesize(query, citations)
            answer.fallback_used = True
            return answer
