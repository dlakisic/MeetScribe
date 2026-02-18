from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
