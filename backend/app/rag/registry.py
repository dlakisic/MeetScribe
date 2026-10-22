"""Provider loading for modular RAG components."""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any

from ..core.llm import LLMFactory
from ..core.logging import get_logger
from ..database import Database
from .embeddings import SegmentEmbedder
from .interfaces import AbstractAnswerSynthesizer, AbstractReranker, AbstractRetriever
from .providers import (
    CitationSynthesizer,
    FallbackSynthesizer,
    HybridRetriever,
    IdentityReranker,
    LLMAnswerSynthesizer,
)
from .service import RAGService

log = get_logger("rag.registry")


def _load_class(path: str, expected_base: type) -> type | None:
    try:
        module_name, class_name = path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        klass = getattr(module, class_name)
    except Exception as exc:
        log.warning(
            "Failed to import RAG provider", extra={"provider_path": path, "error": str(exc)}
        )
        return None

    if not issubclass(klass, expected_base):
        log.warning(
            "Invalid RAG provider type",
            extra={"provider_path": path, "expected_base": expected_base.__name__},
        )
        return None
    return klass


def _instantiate(klass: type, kwargs: dict[str, Any]) -> Any:
    """Instantiate a provider, passing only the kwargs its constructor accepts."""
    params = inspect.signature(klass).parameters
    if not any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        kwargs = {k: v for k, v in kwargs.items() if k in params}
    return klass(**kwargs)


def build_embedder(db: Database) -> SegmentEmbedder | None:
    """Return a segment embedder when LLM_EMBEDDING_MODEL is set and sqlite-vec loads."""
    model = LLMFactory.get_embedding_model()
    if not model:
        return None
    if not db.vector_search_available:
        log.warning("LLM_EMBEDDING_MODEL is set but sqlite-vec is unavailable; ignoring it")
        return None
    log.info("Semantic search enabled", extra={"embedding_model": model})
    return SegmentEmbedder(db, LLMFactory.get_openai_client(), model)


def build_rag_service(db: Database, embedder: SegmentEmbedder | None = None) -> RAGService:
    # Standard deviations a semantic hit must stand out by (model-independent).
    min_z = float(os.getenv("MEETSCRIBE_RAG_VECTOR_MIN_Z") or 3.5)
    retriever: AbstractRetriever = HybridRetriever(db, embedder=embedder, vector_min_z=min_z)
    reranker: AbstractReranker = IdentityReranker()
    synthesizer: AbstractAnswerSynthesizer = FallbackSynthesizer(
        primary=LLMAnswerSynthesizer(), fallback=CitationSynthesizer()
    )

    retriever_path = os.getenv("MEETSCRIBE_RAG_RETRIEVER")
    reranker_path = os.getenv("MEETSCRIBE_RAG_RERANKER")
    synthesizer_path = os.getenv("MEETSCRIBE_RAG_SYNTHESIZER")

    if retriever_path and (klass := _load_class(retriever_path, AbstractRetriever)):
        retriever = _instantiate(klass, {"db": db, "embedder": embedder})
        log.info("Loaded custom retriever", extra={"provider_path": retriever_path})
    if reranker_path and (klass := _load_class(reranker_path, AbstractReranker)):
        reranker = _instantiate(klass, {})
        log.info("Loaded custom reranker", extra={"provider_path": reranker_path})
    if synthesizer_path and (klass := _load_class(synthesizer_path, AbstractAnswerSynthesizer)):
        synthesizer = _instantiate(klass, {})
        log.info("Loaded custom synthesizer", extra={"provider_path": synthesizer_path})

    return RAGService(retriever=retriever, reranker=reranker, synthesizer=synthesizer)
