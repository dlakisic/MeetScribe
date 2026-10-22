from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.core.llm import LLMFactory
from backend.app.schemas.extraction import ActionItem, ExtractedData, MeetingSummary
from backend.app.services.extraction_service import ExtractionService


@pytest.mark.asyncio
async def test_extraction_unconfigured():
    """Test that service returns early if LLM is not configured."""
    with patch("backend.app.core.llm.LLMFactory.is_configured", return_value=False):
        service = ExtractionService()
        result = await service.extract_from_transcript(
            "Some long enough transcript for testing... " * 3
        )

        assert result.summary.abstract == "LLM not configured (skipped)."
        assert result.summary.sentiment == "neutral"
        assert result.action_items == []


@pytest.mark.asyncio
async def test_extraction_too_short():
    """Test that service returns early if transcript is too short."""
    service = ExtractionService()
    result = await service.extract_from_transcript("Too short")

    assert result.summary.abstract == "Transcript too short."
    assert result.summary.sentiment == "neutral"
    assert result.action_items == []


@pytest.mark.asyncio
async def test_extraction_success():
    """Test successful extraction with configured LLM."""
    mock_data = ExtractedData(
        summary=MeetingSummary(
            abstract="Success.",
            topics=["Test"],
            sentiment="positive",
        ),
        action_items=[ActionItem(description="Do it", owner="Me", status="open")],
        decisions=[],
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_data)

    with (
        patch("backend.app.core.llm.LLMFactory.get_client", return_value=mock_client),
        patch("backend.app.core.llm.LLMFactory.get_model_name", return_value="gpt-mock"),
        patch("backend.app.core.llm.LLMFactory.is_configured", return_value=True),
    ):
        service = ExtractionService()
        transcript = "Long transcript " * 10
        result = await service.extract_from_transcript(transcript)

        assert result.summary.sentiment == "positive"
        assert len(result.action_items) == 1
        assert result.action_items[0].owner == "Me"


@pytest.mark.asyncio
async def test_extraction_api_error():
    """Test handling of API error (should raise or handle gracefully depending on implementation)."""
    # Currently implementation lets exception bubble up or returns None?
    # Let's check current implementation: it awaits client.create().
    # If client raises, it bubbles up. This test verifies that behavior or we catch it.

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

    with (
        patch("backend.app.core.llm.LLMFactory.get_client", return_value=mock_client),
        patch("backend.app.core.llm.LLMFactory.get_model_name", return_value="gpt-mock"),
        patch("backend.app.core.llm.LLMFactory.is_configured", return_value=True),
    ):
        service = ExtractionService()
        transcript = "Long transcript " * 10

        with pytest.raises(Exception, match="API Error"):
            await service.extract_from_transcript(transcript)


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, False),
        ({"LLM_BASE_URL": "", "LLM_API_KEY": ""}, False),
        ({"LLM_BASE_URL": "http://host:11434/v1", "LLM_API_KEY": ""}, True),
        ({"LLM_API_KEY": "sk-test"}, True),
        ({"LLM_BASE_URL": "http://host:11434/v1", "LLM_API_KEY": "change_me"}, False),
    ],
)
def test_llm_is_configured(monkeypatch, env, expected):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert LLMFactory.is_configured() is expected


def test_llm_empty_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_MODEL", "")
    client = LLMFactory.get_client()
    assert str(client.client.base_url).startswith("http://localhost:11434/v1")
    assert LLMFactory.get_model_name() == "llama3"
