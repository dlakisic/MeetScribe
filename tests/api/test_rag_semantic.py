"""Semantic (embedding) side of the hybrid RAG retriever."""

import asyncio
import hashlib
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from backend.app.rag.embeddings import EmbeddingIndexer, SegmentEmbedder
from backend.app.rag.providers import HybridRetriever

# Words sharing a concept get the same direction, so synonyms embed close together.
_CONCEPTS = {
    "vacances": 0,
    "conges": 0,
    "congés": 0,
    "budget": 1,
    "argent": 1,
    "embauche": 2,
    "recrutement": 2,
}


def _fake_vector(value: str, offset: float = 0.0) -> list[float]:
    """Concept one-hot plus deterministic per-text noise, like real embeddings.

    `offset` adds a direction shared by every text. It squeezes all cosine
    distances together, mimicking a model with a different distance scale.
    """
    digest = hashlib.sha256(value.encode()).digest()
    vector = [0.0, 0.0, 0.0] + [0.2 + digest[i] / 255 * 0.3 for i in range(5)] + [offset]
    words = value.lower().replace("?", " ").replace(".", " ").split()
    for word in words:
        if word in _CONCEPTS:
            vector[_CONCEPTS[word]] += 1.5
    return vector


class FakeEmbeddingsClient:
    def __init__(self, fail=False, before_return=None, offset=0.0):
        self.offset = offset
        self.fail = fail
        self.before_return = before_return
        self.calls = 0
        self.embeddings = SimpleNamespace(create=self._create)

    async def _create(self, model, input):
        self.calls += 1
        if self.fail:
            raise ConnectionError("embedding host offline")
        if self.before_return:
            await self.before_return()
        data = [
            SimpleNamespace(index=i, embedding=_fake_vector(value, self.offset))
            for i, value in enumerate(input)
        ]
        return SimpleNamespace(data=list(reversed(data)))


async def _seed(test_app, segments):
    service = test_app.state.meeting_service
    meeting_id = await service.create_meeting(title="Semantic", date=datetime(2026, 1, 1))
    await service.repo.save_transcript(meeting_id, segments, "formatted", {})
    return meeting_id


def _seg(text_, start):
    return {"speaker": "Alice", "text": text_, "start": start, "end": start + 2}


async def _embedding_count(db):
    async with db.engine.begin() as conn:
        return (await conn.execute(text("SELECT count(*) FROM segment_embeddings"))).scalar()


@pytest.fixture
def embedder(test_app):
    return SegmentEmbedder(test_app.state.db, FakeEmbeddingsClient(), model="fake", batch_size=2)


@pytest.fixture
def hybrid(test_app, embedder):
    test_app.state.rag_service.retriever = HybridRetriever(test_app.state.db, embedder=embedder)
    return embedder


@pytest.mark.asyncio
async def test_index_missing_embeds_once_and_follows_edits(test_app, embedder, client):
    meeting_id = await _seed(test_app, [_seg("Un", 0), _seg("Deux", 100), _seg("Trois", 200)])

    assert await embedder.index_missing() == 3
    assert await embedder.index_missing() == 0

    details = await test_app.state.meeting_service.get_meeting_details(meeting_id)
    segment_id = details["transcript"]["segments"][0]["id"]
    await client.patch(f"/api/segments/{segment_id}", json={"text": "Texte corrigé"})
    assert await _embedding_count(test_app.state.db) == 2
    assert await embedder.index_missing() == 1

    await client.delete(f"/api/meetings/{meeting_id}")
    assert await _embedding_count(test_app.state.db) == 0


@pytest.mark.asyncio
async def test_index_skips_segments_edited_during_embedding(test_app):
    meeting_id = await _seed(test_app, [_seg("Avant édition", 0)])

    async def edit_segment():
        await test_app.state.meeting_service.repo.update_segment_text(
            (await test_app.state.meeting_service.get_meeting_details(meeting_id))["transcript"][
                "segments"
            ][0]["id"],
            "Après édition",
        )

    racing = SegmentEmbedder(
        test_app.state.db, FakeEmbeddingsClient(before_return=edit_segment), model="fake"
    )
    await racing.index_missing()
    assert await _embedding_count(test_app.state.db) == 0


@pytest.mark.asyncio
async def test_hybrid_finds_synonyms_without_shared_words(client, test_app, hybrid):
    await _seed(test_app, [_seg("Je pose mes congés en août.", 0), _seg("Rien à voir.", 500)])
    await hybrid.index_missing()

    resp = await client.post("/api/rag/ask", json={"query": "Qui part en vacances ?"})
    citations = resp.json()["citations"]
    assert citations and "congés" in citations[0]["text"]


def _filler(count):
    return [_seg(f"Remarque {i} sur le planning du sprint.", 1000 + i * 100) for i in range(count)]


async def _vector_hits(test_app, embedder, query, meeting_ids=None, min_z=3.5):
    vector = await embedder.embed_query(query)
    async with test_app.state.db.session() as session:
        return await embedder.search(session, vector, meeting_ids, limit=50, min_z=min_z)


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [0.0, 6.0], ids=["wide-scale", "squeezed-scale"])
async def test_same_min_z_works_across_distance_scales(test_app, offset):
    embedder = SegmentEmbedder(
        test_app.state.db, FakeEmbeddingsClient(offset=offset), model=f"fake-{offset}"
    )
    await _seed(test_app, [_seg("Je pose mes congés en août.", 0), *_filler(60)])
    await embedder.index_missing()

    hits = await _vector_hits(test_app, embedder, "Qui part en vacances ?")
    assert len(hits) == 1

    # Nothing about hiring in the corpus: no segment stands out.
    assert await _vector_hits(test_app, embedder, "Le recrutement avance ?") == []


@pytest.mark.asyncio
async def test_fixed_distance_cutoff_would_not_transfer_between_scales(test_app):
    """Why min_z exists: unrelated segments sit far apart with one model, close with another."""
    await _seed(test_app, _filler(60))
    filler_distances = {}
    for offset in (0.0, 6.0):
        embedder = SegmentEmbedder(
            test_app.state.db, FakeEmbeddingsClient(offset=offset), model=f"fake-{offset}"
        )
        await embedder.index_missing()
        async with test_app.state.db.session() as session:
            rows = await session.exec(
                text(
                    "SELECT vec_distance_cosine(embedding, :q) FROM segment_embeddings"
                    " WHERE model = :model"
                ),
                params={
                    "q": await embedder.embed_query("Qui part en vacances ?"),
                    "model": embedder.model,
                },
            )
            filler_distances[offset] = [row[0] for row in rows.all()]

    # A fixed 0.5 cutoff would reject every unrelated segment with one model
    # and accept all of them with the other.
    assert min(filler_distances[0.0]) > 0.5
    assert max(filler_distances[6.0]) < 0.5


@pytest.mark.asyncio
async def test_small_scope_keeps_closest_segments(test_app, embedder):
    meeting_id = await _seed(test_app, [_seg("On parle du budget.", 0), _seg("Autre.", 10)])
    await embedder.index_missing()

    hits = await _vector_hits(test_app, embedder, "Le recrutement avance ?", [meeting_id])
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_hybrid_falls_back_to_keywords_when_host_offline(client, test_app):
    offline = SegmentEmbedder(test_app.state.db, FakeEmbeddingsClient(fail=True), model="fake")
    test_app.state.rag_service.retriever = HybridRetriever(test_app.state.db, embedder=offline)
    await _seed(test_app, [_seg("We ship on Friday.", 0)])

    resp = await client.post("/api/rag/ask", json={"query": "When do we ship?"})
    assert resp.status_code == 200
    assert "Friday" in resp.json()["citations"][0]["text"]


@pytest.mark.asyncio
async def test_indexer_runs_on_notify_and_survives_failures(test_app):
    client = FakeEmbeddingsClient(fail=True)
    embedder = SegmentEmbedder(test_app.state.db, client, model="fake")
    indexer = EmbeddingIndexer(embedder, interval=3600)
    await _seed(test_app, [_seg("Un budget", 0)])

    task = asyncio.create_task(indexer.run())
    try:
        while client.calls == 0:
            await asyncio.sleep(0.01)
        client.fail = False
        indexer.notify(1)
        for _ in range(200):
            if await _embedding_count(test_app.state.db) == 1:
                break
            await asyncio.sleep(0.01)
        assert await _embedding_count(test_app.state.db) == 1
    finally:
        task.cancel()
