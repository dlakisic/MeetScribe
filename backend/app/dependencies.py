from fastapi import Depends, Request

from .config import Config
from .core.auth import security, verify_token
from .rag.service import RAGService
from .services.job_store import JobStore
from .services.meeting_service import MeetingService


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_meeting_service(request: Request) -> MeetingService:
    return request.app.state.meeting_service


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_rag_service(request: Request) -> RAGService:
    return request.app.state.rag_service


def require_auth(request: Request, credentials=Depends(security)):
    """Dependency to require authentication on protected endpoints."""
    config = get_config(request)
    request_id = getattr(request.state, "request_id", None)
    verify_token(
        credentials,
        config.api_token,
        request_id=request_id,
        path=str(request.url.path),
    )
