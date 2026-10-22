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
        # `or` rather than a getenv default: docker-compose passes unset vars as "".
        base_url = os.getenv("LLM_BASE_URL") or "http://localhost:11434/v1"
        api_key = os.getenv("LLM_API_KEY") or "ollama"
        client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        return instructor.from_openai(client, mode=instructor.Mode.JSON)

    @staticmethod
    def get_model_name() -> str:
        """Returns the model name."""
        return os.getenv("LLM_MODEL") or "llama3"

    @staticmethod
    def is_configured() -> bool:
        """Check if an LLM endpoint was configured.

        Setting LLM_BASE_URL alone is enough (Ollama needs no API key).
        """
        base_url = os.getenv("LLM_BASE_URL", "")
        api_key = os.getenv("LLM_API_KEY", "")
        if api_key == "change_me":
            return False
        return bool(base_url or api_key)
