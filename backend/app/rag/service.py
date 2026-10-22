"""RAG orchestration service."""

from __future__ import annotations

from .interfaces import AbstractAnswerSynthesizer, AbstractReranker, AbstractRetriever, RAGAnswer


class RAGService:
    def __init__(
        self,
        retriever: AbstractRetriever,
        reranker: AbstractReranker,
        synthesizer: AbstractAnswerSynthesizer,
    ):
        self.retriever = retriever
        self.reranker = reranker
        self.synthesizer = synthesizer

    async def ask(
        self,
        query: str,
        meeting_ids: list[int] | None = None,
        top_k: int = 5,
    ) -> RAGAnswer:
        candidates = await self.retriever.retrieve(
            query=query, meeting_ids=meeting_ids, top_k=max(top_k * 3, 10)
        )
        ranked = await self.reranker.rerank(query=query, candidates=candidates, top_k=top_k)
        return await self.synthesizer.synthesize(query=query, citations=ranked)
