from ..core.llm import LLMFactory
from ..core.llm_observability import LLMObservability
from ..interfaces import AbstractExtractionService
from ..schemas.extraction import ExtractedData, MeetingSummary


class ExtractionService(AbstractExtractionService):
    def __init__(self):
        self.client = LLMFactory.get_client()
        self.model = LLMFactory.get_model_name()
        self.observability = LLMObservability()

    async def extract_from_transcript(
        self, transcript_text: str, context: dict | None = None
    ) -> ExtractedData:
        """
        Extracts structured data (summary, actions, decisions) from a meeting transcript.
        Uses the configured LLM provider (Ollama/OpenAI) and enforces the ExtractedData schema.
        """
        obs_context = dict(context or {})
        obs_context["model"] = self.model

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

        span = self.observability.start_extraction(obs_context, transcript_text)

        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                response_model=ExtractedData,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert AI meeting assistant. Analyze the following "
                            "transcript and extract structured data. Always respond in the "
                            "language of the transcript."
                        ),
                    },
                    {"role": "user", "content": transcript_text},
                ],
                max_retries=1,
            )
            self.observability.finish_success(span, resp.model_dump())
            return resp
        except Exception as exc:
            self.observability.finish_error(span, exc)
            raise
