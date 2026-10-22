from datetime import datetime
from unittest.mock import patch

import openai
import pytest

from backend.app.rag.providers import CitationSynthesizer, LLMAnswerSynthesizer
from backend.app.rag.registry import _instantiate


@pytest.mark.asyncio
async def test_rag_ask_returns_citations(client, test_app):
    service = test_app.state.meeting_service
    meeting_id = await service.create_meeting(title="RAG Meeting", date=datetime(2026, 1, 1))
    await service.repo.save_transcript(
        meeting_id,
        [
            {"speaker": "Alice", "text": "We decided to ship on Friday.", "start": 0, "end": 4},
            {
                "speaker": "Bob",
                "text": "Action item: prepare the release notes.",
                "start": 5,
                "end": 9,
            },
        ],
        "formatted",
        {},
    )

    resp = await client.post(
        "/api/rag/ask",
        json={"query": "When do we ship?", "meeting_ids": [meeting_id], "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"]
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["meeting_id"] == meeting_id


@pytest.mark.asyncio
async def test_rag_ask_no_evidence(client):
    resp = await client.post(
        "/api/rag/ask",
        json={"query": "What was the quantum budget?", "top_k": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == 0.0
    assert data["citations"] == []


async def _seed(test_app, title, segments):
    service = test_app.state.meeting_service
    meeting_id = await service.create_meeting(title=title, date=datetime(2026, 1, 1))
    await service.repo.save_transcript(meeting_id, segments, "formatted", {})
    return meeting_id


@pytest.mark.asyncio
async def test_rag_ignores_stopword_matches(client, test_app):
    await _seed(
        test_app,
        "Stopwords",
        [{"speaker": "Alice", "text": "We are here and we do it.", "start": 0, "end": 2}],
    )
    resp = await client.post("/api/rag/ask", json={"query": "What do we do?", "top_k": 3})
    assert resp.status_code == 200
    assert resp.json()["citations"] == []


@pytest.mark.asyncio
async def test_rag_finds_old_meetings(client, test_app):
    old_id = await _seed(
        test_app,
        "Old",
        [{"speaker": "Alice", "text": "The budget is approved.", "start": 0, "end": 2}],
    )
    noise = [
        {"speaker": "Bob", "text": f"Unrelated chatter {i}", "start": i, "end": i + 1}
        for i in range(50)
    ]
    await _seed(test_app, "Recent", noise)

    resp = await client.post("/api/rag/ask", json={"query": "Is the budget approved?"})
    assert resp.status_code == 200
    citations = resp.json()["citations"]
    assert citations and citations[0]["meeting_id"] == old_id


@pytest.mark.asyncio
async def test_citation_confidence_is_query_coverage():
    from backend.app.rag.interfaces import RAGChunk

    chunk = RAGChunk(1, 1, "Alice", "We ship on Friday.", 0.0, 1.0, score=9.9)
    answer = await CitationSynthesizer().synthesize("ship release Friday", [chunk])
    assert answer.confidence == pytest.approx(2 / 3, abs=1e-3)


@pytest.mark.asyncio
async def test_rag_llm_unreachable_returns_503(client, test_app):
    await _seed(
        test_app,
        "LLM",
        [{"speaker": "Alice", "text": "We ship on Friday.", "start": 0, "end": 2}],
    )
    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        synthesizer = LLMAnswerSynthesizer()
    synthesizer.client.chat.completions.create = _raise_connection_error
    test_app.state.rag_service.synthesizer = synthesizer

    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        resp = await client.post("/api/rag/ask", json={"query": "When do we ship?"})
    assert resp.status_code == 503


async def _raise_connection_error(*args, **kwargs):
    raise openai.APIConnectionError(request=None)


def test_instantiate_passes_only_accepted_kwargs():
    class NoArgs:
        def __init__(self):
            pass

    class Broken:
        def __init__(self, db):
            raise TypeError("bug inside constructor")

    assert isinstance(_instantiate(NoArgs, {"db": object()}), NoArgs)
    with pytest.raises(TypeError, match="bug inside constructor"):
        _instantiate(Broken, {"db": object()})


@pytest.mark.asyncio
async def test_rag_matches_inflections_and_accents(client, test_app):
    meeting_id = await _seed(
        test_app,
        "Planning",
        [
            {"speaker": "Alice", "text": "La livraison est prévue vendredi.", "start": 0, "end": 3},
            {"speaker": "Bob", "text": "Nous avons pris une décision.", "start": 300, "end": 303},
        ],
    )
    resp = await client.post("/api/rag/ask", json={"query": "Quand est-ce qu'on livre ?"})
    citations = resp.json()["citations"]
    assert citations and "livraison" in citations[0]["text"]

    resp = await client.post("/api/rag/ask", json={"query": "Qu'a-t-on decide ?"})
    citations = resp.json()["citations"]
    assert citations and citations[0]["meeting_id"] == meeting_id
    assert "décision" in citations[0]["text"]


@pytest.mark.asyncio
async def test_rag_merges_nearby_turns_into_one_window(client, test_app):
    meeting_id = await _seed(
        test_app,
        "Infra sync",
        [
            {"speaker": "Alice", "text": "On part sur quel hébergement ?", "start": 0, "end": 3},
            {"speaker": "Bob", "text": "L'option B, chez OVH.", "start": 3, "end": 5},
            {"speaker": "Alice", "text": "Autre sujet sans rapport.", "start": 600, "end": 602},
        ],
    )
    resp = await client.post("/api/rag/ask", json={"query": "Quelle option pour l'hébergement ?"})
    citations = resp.json()["citations"]
    assert len(citations) == 1
    window = citations[0]
    assert len(window["segment_ids"]) == 2
    assert window["text"] == "Alice: On part sur quel hébergement ?\nBob: L'option B, chez OVH."
    assert window["start_time"] == 0 and window["end_time"] == 5
    assert window["meeting_id"] == meeting_id
    assert window["meeting_title"] == "Infra sync"
    assert window["meeting_date"].startswith("2026-01-01")


@pytest.mark.asyncio
async def test_rag_bm25_prefers_rare_terms(client, test_app):
    common = [
        {
            "speaker": "Bob",
            "text": f"Point projet numéro {i}.",
            "start": i * 100,
            "end": i * 100 + 2,
        }
        for i in range(10)
    ]
    rare = [
        {"speaker": "Alice", "text": "Le projet Kubernetes avance.", "start": 5000, "end": 5002}
    ]
    await _seed(test_app, "Weekly", common + rare)

    resp = await client.post("/api/rag/ask", json={"query": "projet kubernetes"})
    assert "Kubernetes" in resp.json()["citations"][0]["text"]


@pytest.mark.asyncio
async def test_rag_index_follows_edits_and_deletes(client, test_app):
    meeting_id = await _seed(
        test_app,
        "Edits",
        [{"speaker": "Alice", "text": "Typo dans le transcript.", "start": 0, "end": 2}],
    )
    segment_id = (await test_app.state.meeting_service.get_meeting_details(meeting_id))[
        "transcript"
    ]["segments"][0]["id"]

    await client.patch(f"/api/segments/{segment_id}", json={"text": "Le budget marketing."})
    resp = await client.post("/api/rag/ask", json={"query": "budget marketing"})
    assert resp.json()["citations"][0]["segment_id"] == segment_id
    resp = await client.post("/api/rag/ask", json={"query": "typo transcript"})
    assert resp.json()["citations"] == []

    await client.delete(f"/api/meetings/{meeting_id}")
    resp = await client.post("/api/rag/ask", json={"query": "budget marketing"})
    assert resp.json()["citations"] == []


@pytest.mark.asyncio
async def test_rag_query_with_fts_syntax_is_safe(client, test_app):
    await _seed(
        test_app,
        "Syntax",
        [{"speaker": "Alice", "text": "Revue du code NEAR la release.", "start": 0, "end": 2}],
    )
    resp = await client.post("/api/rag/ask", json={"query": 'release" OR NEAR(code) AND -* "'})
    assert resp.status_code == 200


def _chunk(segment_id, text):
    from backend.app.rag.interfaces import RAGChunk

    return RAGChunk(1, segment_id, "Alice", text, 0.0, 1.0, segment_ids=[segment_id])


def _llm_synth(used_sources, answer="Réponse [2]"):
    from unittest.mock import AsyncMock, MagicMock

    synth = LLMAnswerSynthesizer()
    synth.client = MagicMock()
    synth.client.chat.completions.create = AsyncMock(
        return_value=MagicMock(answer=answer, used_sources=used_sources)
    )
    return synth


@pytest.mark.asyncio
async def test_llm_synth_keeps_only_used_sources():
    chunks = [_chunk(1, "Rien à voir."), _chunk(2, "Le budget est validé."), _chunk(3, "Autre.")]
    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        answer = await _llm_synth([2, 2, 99]).synthesize("budget validé", chunks)
    assert [c.segment_id for c in answer.citations] == [2]
    assert answer.confidence == 1.0
    assert answer.fallback_used is False


@pytest.mark.asyncio
async def test_llm_synth_no_used_sources_means_no_citations():
    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        answer = await _llm_synth([], "Les extraits ne répondent pas.").synthesize(
            "budget", [_chunk(1, "Le budget est validé.")]
        )
    assert answer.citations == []
    assert answer.confidence == 0.0


@pytest.mark.asyncio
async def test_rag_falls_back_when_llm_unreachable(client, test_app):
    from backend.app.rag.providers import FallbackSynthesizer

    await _seed(
        test_app,
        "Fallback",
        [{"speaker": "Alice", "text": "We ship on Friday.", "start": 0, "end": 2}],
    )
    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        llm = LLMAnswerSynthesizer()
    llm.client.chat.completions.create = _raise_connection_error
    test_app.state.rag_service.synthesizer = FallbackSynthesizer(llm, CitationSynthesizer())

    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=True):
        resp = await client.post("/api/rag/ask", json={"query": "When do we ship?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["fallback_used"] is True
    assert "Friday" in data["citations"][0]["text"]


@pytest.mark.asyncio
async def test_rag_falls_back_when_llm_not_configured(client, test_app, monkeypatch):
    from backend.app.rag.registry import build_rag_service

    # A developer's real embedding config must not make this test call the network.
    monkeypatch.delenv("LLM_EMBEDDING_MODEL", raising=False)

    await _seed(
        test_app,
        "No LLM",
        [{"speaker": "Alice", "text": "We ship on Friday.", "start": 0, "end": 2}],
    )
    test_app.state.rag_service = build_rag_service(test_app.state.db)
    with patch("backend.app.rag.providers.LLMFactory.is_configured", return_value=False):
        resp = await client.post("/api/rag/ask", json={"query": "When do we ship?"})
    assert resp.status_code == 200
    assert resp.json()["fallback_used"] is True


@pytest.mark.asyncio
async def test_rag_ignores_question_words(client, test_app):
    """Found by rag_eval: 'quel' alone used to match any segment asking a question."""
    await _seed(
        test_app,
        "Questions",
        [{"speaker": "Alice", "text": "On part sur quel hébergement ?", "start": 0, "end": 2}],
    )
    resp = await client.post(
        "/api/rag/ask", json={"query": "Quel est le budget du séminaire au Japon ?"}
    )
    assert resp.json()["citations"] == []
