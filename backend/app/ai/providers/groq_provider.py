"""Groq Provider — uses Groq's OpenAI-compatible API."""
from typing import Optional

from app.ai.providers.openai_provider import OpenAIProvider
from app.config import settings


class GroqProvider(OpenAIProvider):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        super().__init__(
            api_key=api_key or settings.GROQ_API_KEY,
            model=model or settings.GROQ_MODEL,
            base_url="https://api.groq.com/openai/v1",
            api_key_name="GROQ_API_KEY",
            provider_name="Groq",
        )
