"""Tests for authentication middleware."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core.auth import verify_token


def test_no_token_configured_allows_all():
    """When api_token is None, all requests pass."""
    verify_token(None, expected_token=None)  # Should not raise


def test_token_required_but_missing():
    """When api_token is set but no credentials provided, reject."""
    with pytest.raises(Exception) as exc_info:
        verify_token(None, expected_token="secret")
    assert exc_info.value.status_code == 401


def test_token_invalid():
    """Wrong token should be rejected."""
    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
    with pytest.raises(Exception) as exc_info:
        verify_token(creds, expected_token="secret")
    assert exc_info.value.status_code == 401


def test_token_valid():
    """Correct token should pass."""
    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
    verify_token(creds, expected_token="secret")  # Should not raise


@pytest.mark.asyncio
async def test_protected_route_without_token(test_app, test_config):
    """Full integration: configure token and verify routes require it."""
    test_config.api_token = "my-secret"

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/transcripts")
        assert resp.status_code == 401

    # Reset
    test_config.api_token = None


@pytest.mark.asyncio
async def test_protected_route_with_valid_token(test_app, test_config):
    """Full integration: valid token allows access."""
    test_config.api_token = "my-secret"

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get(
            "/api/transcripts",
            headers={"Authorization": "Bearer my-secret"},
        )
        assert resp.status_code == 200

    # Reset
    test_config.api_token = None
