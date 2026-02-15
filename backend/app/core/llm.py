import os

import instructor
from openai import AsyncOpenAI


class LLMFactory:
    """Factory to create configured LLM clients for structured extraction."""

    @staticmethod
    def get_client() -> instructor.Instructor:
        """
        Returns an async instructor-patched client for local inference.
        Defaults to Ollama (http://localhost:11434/v1).
        Override with LLM_BASE_URL for any OpenAI-compatible provider.
        """
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.getenv("LLM_API_KEY", "ollama")
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        return instructor.from_openai(client, mode=instructor.Mode.JSON)

    @staticmethod
    def get_model_name() -> str:
        """Returns the model name."""
        return os.getenv("LLM_MODEL", "llama3")

    @staticmethod
    def is_configured() -> bool:
        """Check if the LLM is properly configured."""
        api_key = os.getenv("LLM_API_KEY", "")
        return bool(api_key) and api_key not in ("change_me", "")
