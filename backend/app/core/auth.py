"""Authentication utilities."""

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .logging import get_logger

security = HTTPBearer(auto_error=False)
log = get_logger("auth")


def verify_token(
    credentials: HTTPAuthorizationCredentials | None,
    expected_token: str | None,
    request_id: str | None = None,
    path: str | None = None,
) -> None:
    """Verify Bearer token authentication.

    Args:
        credentials: The Authorization header credentials
        expected_token: The expected token (from config)

    Raises:
        HTTPException: 401 if token is required but missing/invalid
    """
    if expected_token is None:
        return

    if credentials is None:
        log.warning(
            "Unauthorized request: missing token",
            extra={"request_id": request_id, "path": path},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != expected_token:
        log.warning(
            "Unauthorized request: invalid token",
            extra={"request_id": request_id, "path": path},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
