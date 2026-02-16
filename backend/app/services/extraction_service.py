from ..core.llm import LLMFactory
from ..interfaces import AbstractExtractionService
from ..schemas.extraction import ExtractedData, MeetingSummary


class ExtractionService(AbstractExtractionService):
    def __init__(self):
        self.client = LLMFactory.get_client()
        self.model = LLMFactory.get_model_name()

    async def extract_from_transcript(self, transcript_text: str) -> ExtractedData:
        """
        Extracts structured data (summary, actions, decisions) from a meeting transcript.
        Uses the configured LLM provider (Ollama/OpenAI) and enforces the ExtractedData schema.
        """
        if not transcript_text or len(transcript_text) < 50:
            return ExtractedData(
                summary=MeetingSummary(
                    abstract="Transcript too short.", topics=[], sentiment="neutral"
                ),
                action_items=[],
                decisions=[],
            )

        if not LLMFactory.is_configured():
            return ExtractedData(
                summary=MeetingSummary(
                    abstract="LLM not configured (skipped).", topics=[], sentiment="neutral"
                ),
                action_items=[],
                decisions=[],
            )

        resp = await self.client.chat.completions.create(
            model=self.model,
            response_model=ExtractedData,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert AI meeting assistant. Analyze the following transcript and extract structured data. Always respond in the language of the transcript.",
                },
                {"role": "user", "content": transcript_text},
            ],
            max_retries=1,
        )
        return resp
