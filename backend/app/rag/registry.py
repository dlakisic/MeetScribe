"""Provider loading for modular RAG components."""

from __future__ import annotations

import importlib
import inspect
import os
from typing import Any

from ..core.logging import get_logger
from ..database import Database
from .interfaces import AbstractAnswerSynthesizer, AbstractReranker, AbstractRetriever
from .providers import IdentityReranker, KeywordRetriever, LLMAnswerSynthesizer
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


def build_rag_service(db: Database) -> RAGService:
    retriever: AbstractRetriever = KeywordRetriever(db)
    reranker: AbstractReranker = IdentityReranker()
    synthesizer: AbstractAnswerSynthesizer = LLMAnswerSynthesizer()

    retriever_path = os.getenv("MEETSCRIBE_RAG_RETRIEVER")
    reranker_path = os.getenv("MEETSCRIBE_RAG_RERANKER")
    synthesizer_path = os.getenv("MEETSCRIBE_RAG_SYNTHESIZER")

    if retriever_path and (klass := _load_class(retriever_path, AbstractRetriever)):
        retriever = _instantiate(klass, {"db": db})
        log.info("Loaded custom retriever", extra={"provider_path": retriever_path})
    if reranker_path and (klass := _load_class(reranker_path, AbstractReranker)):
        reranker = _instantiate(klass, {})
        log.info("Loaded custom reranker", extra={"provider_path": reranker_path})
    if synthesizer_path and (klass := _load_class(synthesizer_path, AbstractAnswerSynthesizer)):
        synthesizer = _instantiate(klass, {})
        log.info("Loaded custom synthesizer", extra={"provider_path": synthesizer_path})

    return RAGService(retriever=retriever, reranker=reranker, synthesizer=synthesizer)
