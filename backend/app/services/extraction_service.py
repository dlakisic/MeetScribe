from ..core.llm import LLMFactory
from ..schemas.extraction import ExtractedData


class ExtractionService:
    def __init__(self):
        self.client = LLMFactory.get_client()
        self.model = LLMFactory.get_model_name()

    async def extract_from_transcript(self, transcript_text: str) -> ExtractedData:
        """
        Extracts structured data (summary, actions, decisions) from a meeting transcript.
        Uses the configured LLM provider (Ollama/OpenAI) and enforces the ExtractedData schema.
        """
        if not transcript_text or len(transcript_text) < 50:
            # Return empty structure if transcript is too short
            return ExtractedData(
                summary={"abstract": "Transcript too short.", "topics": [], "sentiment": "neutral"},
                action_items=[],
                decisions=[],
            )

        resp = self.client.chat.completions.create(
            model=self.model,
            response_model=ExtractedData,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert AI meeting assistant. Analyze the following transcript and extract structured data.",
                },
                {"role": "user", "content": transcript_text},
            ],
            max_retries=3,
        )
        return resp
