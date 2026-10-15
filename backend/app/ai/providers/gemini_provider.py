"""Google Gemini provider with explicit function calling."""
import asyncio
import json
import logging
import re
import secrets
from typing import Any, Dict, List, Optional

from app.ai.providers.base import AIProvider
from app.config import settings

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or settings.GEMINI_API_KEY or "").strip()
        self.model = (model or settings.DEFAULT_MODEL or "gemini-3.8-flash").strip()
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and len(self.api_key) > 20

    def _get_client(self):
        if not self.is_configured:
            return None
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _generate_sync(
        self,
        contents: list[Any],
        system_instruction: str,
        tools: list[Any],
        temperature: float,
        max_tokens: int,
    ) -> Any:
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction or None,
            tools=tools or None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        last_error = None
        for attempt in range(1, 4):
            try:
                return self._get_client().models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            except Exception as error:
                last_error = error
                text = str(error)
                logger.warning("Gemini attempt %s failed: %s", attempt, text)
                if "503" not in text and "UNAVAILABLE" not in text and "high demand" not in text.lower():
                    raise
                import time
                time.sleep(attempt * 2)
        raise last_error

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        if not self.is_configured:
            return {"content": "Gemini belum dikonfigurasi.", "tool_calls": None, "usage": {}}

        from google.genai import types

        system_parts: list[str] = []
        contents: list[Any] = []
        for message in messages:
            role = message.get("role")
            content = message.get("content") or ""
            if role == "system":
                system_parts.append(content)
            elif role in {"user", "assistant"} and message.get("tool_calls"):
                calls = []
                for call in message["tool_calls"]:
                    function = call.get("function", {})
                    raw_args = function.get("arguments", "{}")
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    calls.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                id=call.get("id"),
                                name=function.get("name"),
                                args=args,
                            )
                        )
                    )
                contents.append(types.Content(role="model", parts=calls))
            elif role == "tool":
                try:
                    response = json.loads(content)
                except (TypeError, json.JSONDecodeError):
                    response = {"result": content}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=message.get("name", ""),
                                response=response,
                            )
                        ],
                    )
                )
            elif role in {"user", "assistant"} and content:
                contents.append(
                    types.Content(
                        role="user" if role == "user" else "model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        declarations = []
        for item in tools or []:
            function = item.get("function", {})
            if function.get("name"):
                declarations.append(
                    types.FunctionDeclaration(
                        name=function["name"],
                        description=function.get("description", ""),
                        parameters_json_schema=function.get("parameters", {"type": "object"}),
                    )
                )
        gemini_tools = [types.Tool(function_declarations=declarations)] if declarations else []

        try:
            response = await asyncio.to_thread(
                self._generate_sync,
                contents,
                "\n".join(system_parts),
                gemini_tools,
                temperature,
                max_tokens,
            )
            calls = []
            for call in getattr(response, "function_calls", None) or []:
                calls.append(
                    {
                        "id": getattr(call, "id", None) or secrets.token_hex(12),
                        "name": call.name,
                        "args": dict(call.args or {}),
                    }
                )
            content = getattr(response, "text", None) or ""
            if not content and not calls:
                content = "Gemini tidak mengembalikan teks."
            return {"content": content, "tool_calls": calls or None, "usage": {}}
        except Exception as error:
            logger.exception("Gemini chat failed")
            text = str(error)
            error_code = (
                getattr(error, "code", None)
                or getattr(error, "status_code", None)
            )
            try:
                error_code = int(error_code)
            except (TypeError, ValueError):
                match = re.search(r"\b(429|503)\b", text)
                error_code = int(match.group(1)) if match else None
            if error_code == 429:
                return {
                    "content": (
                        "Kuota Gemini sedang habis. Tunggu hingga kuota direset, "
                        "naikkan limit, atau gunakan provider AI lain."
                    ),
                    "tool_calls": None,
                    "usage": {},
                    "error_code": 429,
                    "error_category": "quota_exceeded",
                }
            if "503" in text or "UNAVAILABLE" in text:
                return {
                    "content": "Gemini sedang sibuk. Coba lagi sebentar.",
                    "tool_calls": None,
                    "usage": {},
                    "error_code": error_code or 503,
                    "error_category": "temporarily_unavailable",
                }
            return {"content": "Gemini gagal memproses permintaan. Coba lagi nanti.", "tool_calls": None, "usage": {}}

    def _embed_sync(self, texts: List[str]) -> List[List[float]]:
        response = self._get_client().models.embed_content(
            model="gemini-embedding-001",
            contents=texts,
        )
        embeddings = getattr(response, "embeddings", None) or []
        vectors = [list(item.values) for item in embeddings]
        if len(vectors) != len(texts):
            raise RuntimeError("Gemini returned an incomplete embedding response.")
        return vectors

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.is_configured:
            raise RuntimeError("GEMINI_API_KEY belum dikonfigurasi.")
        try:
            return await asyncio.to_thread(self._embed_sync, texts)
        except Exception as error:
            logger.exception("Gemini embedding failed")
            raise RuntimeError("Gemini embedding request failed.") from error
