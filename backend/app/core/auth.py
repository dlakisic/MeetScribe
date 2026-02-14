"""Authentication utilities."""

from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Optional bearer token - returns None if no auth header
security = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials | None,
    expected_token: str | None,
) -> None:
    """Verify Bearer token authentication.

    Args:
        credentials: The Authorization header credentials
        expected_token: The expected token (from config)

    Raises:
        HTTPException: 401 if token is required but missing/invalid
    """
    # If no token configured, allow all requests
    if expected_token is None:
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
