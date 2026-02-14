import os

import instructor
from openai import OpenAI


class LLMFactory:
    """Factory to create configured LLM clients for structured extraction."""

    @staticmethod
    def get_client() -> instructor.Instructor:
        """
        Returns an instructor-patched client for local inference.
        Defaults to Ollama (http://localhost:11434/v1).
        """
        # Default to local Ollama instance
        base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        api_key = os.getenv("LLM_API_KEY", "ollama")  # generic key required by client

        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )
        return instructor.from_openai(client, mode=instructor.Mode.JSON)

    @staticmethod
    def get_model_name() -> str:
        """Returns the model name."""
        return os.getenv("LLM_MODEL", "llama3")
