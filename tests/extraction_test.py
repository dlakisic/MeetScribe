from unittest.mock import MagicMock, patch

import pytest

from backend.app.schemas.extraction import ActionItem, ExtractedData, MeetingSummary
from backend.app.services.extraction_service import ExtractionService


@pytest.mark.asyncio
async def test_extraction_service_logic():
    # Mock LLM response object
    mock_data = ExtractedData(
        summary=MeetingSummary(
            abstract="Discussed project roadmap.",
            topics=["Roadmap", "Phase 6"],
            sentiment="positive",
        ),
        action_items=[ActionItem(description="Implement test", owner="Dino", status="open")],
        decisions=[],
    )

    # Mock the client
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_data

    # Patch the factory to return our mock client
    with (
        patch("backend.app.core.llm.LLMFactory.get_client", return_value=mock_client),
        patch("backend.app.core.llm.LLMFactory.get_model_name", return_value="gpt-mock"),
    ):
        service = ExtractionService()

        # Use a long enough transcript to avoid "too short" check
        transcript = (
            "This is a meeting about the roadmap. We need to implement the test. Dino will do it. "
            * 5
        )

        result = await service.extract_from_transcript(transcript)

        assert result.summary.sentiment == "positive"
        assert len(result.action_items) == 1
        assert result.action_items[0].owner == "Dino"
