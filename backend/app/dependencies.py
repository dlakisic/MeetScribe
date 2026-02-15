from fastapi import Depends, Request

from .config import Config
from .core.auth import security, verify_token
from .services.job_store import JobStore
from .services.meeting_service import MeetingService


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_meeting_service(request: Request) -> MeetingService:
    return request.app.state.meeting_service


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def require_auth(request: Request, credentials=Depends(security)):
    """Dependency to require authentication on protected endpoints."""
    config = get_config(request)
    verify_token(credentials, config.api_token)
