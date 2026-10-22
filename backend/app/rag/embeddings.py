"""Segment embeddings for semantic RAG search.

Vectors come from an OpenAI-compatible embeddings endpoint (Ollama by default) and
are stored in the segment_embeddings table; sqlite-vec computes distances in SQL.
The GPU host serving Ollama may be asleep, so every call here degrades gracefully.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass

import sqlite_vec
from openai import AsyncOpenAI
from sqlalchemy import bindparam, text

from ..core.logging import get_logger
from ..database import Database

log = get_logger("rag.embeddings")


@dataclass
class VectorHit:
    id: int
    meeting_id: int
    start_time: float
    end_time: float
    distance: float


class SegmentEmbedder:
    def __init__(
        self,
        db: Database,
        client: AsyncOpenAI,
        model: str,
        batch_size: int = 32,
        query_timeout: float = 5.0,
    ):
        self._db = db
        self._client = client
        self.model = model
        self._batch_size = batch_size
        self._query_timeout = query_timeout

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]

    async def embed_query(self, query: str) -> bytes | None:
        """Embed a search query, or return None if the endpoint is unreachable."""
        try:
            [vector] = await asyncio.wait_for(self._embed([query]), self._query_timeout)
        except Exception as exc:
            log.warning("Query embedding failed, keyword search only", extra={"error": str(exc)})
            return None
        return sqlite_vec.serialize_float32(vector)

    async def search(
        self,
        session,
        query_vector: bytes,
        meeting_ids: list[int] | None,
        limit: int,
        min_z: float,
        min_population: int = 30,
        small_scope_keep: int = 3,
    ) -> list[VectorHit]:
        """Return segments that stand out as unusually close to the query.

        Distance scales differ between embedding models (unrelated texts can be
        0.4 apart with one model and 0.8 with another), so instead of a fixed
        cutoff a hit must be at least `min_z` standard deviations closer than the
        mean distance of the searched segments. Scopes smaller than
        `min_population` are too small for meaningful statistics: the closest
        `small_scope_keep` segments are returned instead.
        """
        scope = "AND s.meeting_id IN :meeting_ids" if meeting_ids else ""
        # Window functions see every scoped segment before ORDER BY/LIMIT apply.
        stmt = text(
            "SELECT id, meeting_id, start_time, end_time, distance,"
            "       AVG(distance) OVER () AS mean,"
            "       AVG(distance * distance) OVER () AS mean_sq,"
            "       COUNT(*) OVER () AS population"
            " FROM ("
            "  SELECT s.id, s.meeting_id, s.start_time, s.end_time,"
            "         vec_distance_cosine(e.embedding, :query) AS distance"
            "  FROM segment_embeddings e JOIN segments s ON s.id = e.segment_id"
            f" WHERE e.model = :model {scope}"
            ") ORDER BY distance LIMIT :limit"
        )
        params = {"query": query_vector, "model": self.model, "limit": limit}
        if meeting_ids:
            stmt = stmt.bindparams(bindparam("meeting_ids", expanding=True))
            params["meeting_ids"] = meeting_ids
        rows = (await session.exec(stmt, params=params)).all()
        if not rows:
            return []

        hits = [VectorHit(r.id, r.meeting_id, r.start_time, r.end_time, r.distance) for r in rows]
        first = rows[0]
        if first.population < min_population:
            return hits[:small_scope_keep]

        variance = max(0.0, first.mean_sq - first.mean**2)
        if variance < 1e-12:
            # All segments equally distant: nothing stands out.
            return []
        threshold = min_z**2 * variance
        return [
            h
            for h in hits
            if h.distance < first.mean and (first.mean - h.distance) ** 2 >= threshold
        ]

    async def index_missing(self) -> int:
        """Embed segments that have no vector for the current model. Returns the count."""
        total = 0
        while True:
            async with self._db.session() as session:
                rows = (
                    await session.exec(
                        text(
                            "SELECT s.id, s.text FROM segments s"
                            " LEFT JOIN segment_embeddings e"
                            "   ON e.segment_id = s.id AND e.model = :model"
                            " WHERE e.segment_id IS NULL AND trim(s.text) != ''"
                            " ORDER BY s.id LIMIT :limit"
                        ),
                        params={"model": self.model, "limit": self._batch_size},
                    )
                ).all()
            if not rows:
                return total

            vectors = await self._embed([row.text for row in rows])

            inserted = 0
            async with self._db.session() as session:
                for row, vector in zip(rows, vectors, strict=True):
                    # Skip segments deleted or edited while the batch was being embedded.
                    result = await session.exec(
                        text(
                            "INSERT OR REPLACE INTO segment_embeddings"
                            " (segment_id, model, embedding)"
                            " SELECT :id, :model, :embedding WHERE EXISTS"
                            " (SELECT 1 FROM segments WHERE id = :id AND text = :text)"
                        ),
                        params={
                            "id": row.id,
                            "model": self.model,
                            "embedding": sqlite_vec.serialize_float32(vector),
                            "text": row.text,
                        },
                    )
                    inserted += result.rowcount
                await session.commit()
            total += inserted
            if not inserted:
                # Whole batch changed under us; the next periodic pass will retry it.
                return total


class EmbeddingIndexer:
    """Background loop that keeps segment embeddings up to date.

    Runs after each new transcript (via notify) and periodically, which also
    retries batches that failed while the embedding host was offline and picks
    up edited segments.
    """

    def __init__(self, embedder: SegmentEmbedder, interval: float = 300.0):
        self._embedder = embedder
        self._interval = interval
        self._wake = asyncio.Event()

    def notify(self, *_args) -> None:
        self._wake.set()

    async def run(self) -> None:
        while True:
            self._wake.clear()
            try:
                count = await self._embedder.index_missing()
                if count:
                    log.info(f"Embedded {count} segments with {self._embedder.model}")
            except Exception as exc:
                log.warning("Embedding indexing failed, will retry", extra={"error": str(exc)})
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), self._interval)
