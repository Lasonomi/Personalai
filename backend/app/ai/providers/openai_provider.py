"""OpenAI Provider — real implementation"""
from typing import Any, Dict, List, Optional
import logging
from app.ai.providers.base import AIProvider
from app.config import settings

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        *,
        base_url: Optional[str] = None,
        api_key_name: str = "OPENAI_API_KEY",
        provider_name: str = "OpenAI",
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.DEFAULT_MODEL
        self.base_url = base_url
        self.api_key_name = api_key_name
        self.provider_name = provider_name
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            if not self.api_key:
                raise ValueError(f"{self.api_key_name} is not set in .env")
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        client = self._get_client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message

            tool_calls = None
            if message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": tc.function.arguments,
                    }
                    for tc in message.tool_calls
                ]

            return {
                "content": message.content or "",
                "tool_calls": tool_calls,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                },
            }
        except Exception as e:
            logger.exception("%s chat failed", self.provider_name)
            return {
                "content": f"{self.provider_name} gagal memproses permintaan. Coba lagi nanti.",
                "tool_calls": None,
                "usage": {},
            }

    async def embed(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        try:
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.exception("%s embed failed", self.provider_name)
            raise RuntimeError(f"{self.provider_name} embedding request failed.") from e
