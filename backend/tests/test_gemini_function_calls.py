from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

from app.ai.orchestrator import orchestrator
from app.ai.providers.gemini_provider import GeminiProvider


class GeminiFunctionCallTests(unittest.IsolatedAsyncioTestCase):
    async def test_function_call_is_translated_to_tool_registry_shape(self):
        provider = GeminiProvider(api_key="x" * 32)

        def fake_generate(contents, system, tools, temperature, max_tokens):
            self.assertEqual(len(tools), 1)
            self.assertEqual(tools[0].function_declarations[0].name, "create_task")
            return SimpleNamespace(
                function_calls=[
                    SimpleNamespace(
                        id="gemini-call-1",
                        name="create_task",
                        args={"title": "laporan"},
                    )
                ],
                text=None,
            )

        provider._generate_sync = fake_generate
        response = await provider.chat(
            [
                {"role": "system", "content": "Use tools."},
                {"role": "user", "content": "Buat task laporan"},
            ],
            tools=[
                tool
                for tool in orchestrator.tools.definitions()
                if tool["function"]["name"] == "create_task"
            ],
        )
        self.assertEqual(response["tool_calls"][0]["name"], "create_task")
        self.assertEqual(response["tool_calls"][0]["args"], {"title": "laporan"})

    async def test_function_result_round_trip_content_is_supported(self):
        provider = GeminiProvider(api_key="x" * 32)
        received = {}

        def fake_generate(contents, system, tools, temperature, max_tokens):
            received["contents"] = contents
            return SimpleNamespace(function_calls=None, text="Tugas berhasil.")

        provider._generate_sync = fake_generate
        response = await provider.chat(
            [
                {"role": "assistant", "content": None, "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "create_task",
                            "arguments": '{"title":"laporan"}',
                        },
                    }
                ]},
                {
                    "role": "tool",
                    "name": "create_task",
                    "content": '{"success":true,"title":"laporan"}',
                },
            ],
            tools=[],
        )
        self.assertEqual(response["content"], "Tugas berhasil.")
        self.assertEqual(len(received["contents"]), 2)

    async def test_quota_error_is_returned_as_structured_provider_status(self):
        provider = GeminiProvider(api_key="x" * 32)

        class QuotaError(Exception):
            status_code = 429

        def fail_generate(*args):
            raise QuotaError("quota exceeded")

        provider._generate_sync = fail_generate
        response = await provider.chat(
            [{"role": "user", "content": "Malam ini hujan di Lumajang?"}],
            tools=[],
        )

        self.assertEqual(response["error_code"], 429)
        self.assertEqual(response["error_category"], "quota_exceeded")
        self.assertNotIn("quota exceeded", response["content"])

    async def test_quota_error_uses_tavily_for_factual_questions(self):
        from app.ai.orchestrator import AIOrchestrator

        provider = SimpleNamespace(
            chat=AsyncMock(
                return_value={
                    "content": "Kuota Gemini sedang habis.",
                    "tool_calls": None,
                    "error_code": 429,
                    "error_category": "quota_exceeded",
                }
            )
        )
        assistant = AIOrchestrator(provider)
        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        search_result = {
            "success": True,
            "answer": "Kemungkinan hujan ringan malam ini.",
            "results": [
                {
                    "title": "Prakiraan Lumajang",
                    "url": "https://weather.example/lumajang",
                }
            ],
        }
        assistant.tools.execute = AsyncMock(return_value=search_result)
        assistant._build_context = AsyncMock(return_value={})

        reply = await assistant._process_with_ai(
            "malam ini hujan ga di lumajang",
            user,
            "discord",
            "123",
            [],
        )

        self.assertIn("Kemungkinan hujan ringan", reply)
        self.assertIn("https://weather.example/lumajang", reply)
        assistant.tools.execute.assert_awaited_once_with(
            "search_web",
            {"query": "malam ini hujan ga di lumajang", "max_results": 5},
            user.id,
        )

    async def test_quota_error_does_not_web_search_action_requests(self):
        from app.ai.orchestrator import AIOrchestrator

        provider = SimpleNamespace(
            chat=AsyncMock(
                return_value={
                    "content": "Kuota Gemini sedang habis.",
                    "tool_calls": None,
                    "error_code": 429,
                    "error_category": "quota_exceeded",
                }
            )
        )
        assistant = AIOrchestrator(provider)
        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        assistant.tools.execute = AsyncMock()
        assistant._build_context = AsyncMock(return_value={})

        reply = await assistant._process_with_ai(
            "tolong buatkan jadwal kuliah besok",
            user,
            "discord",
            "123",
            [],
        )

        self.assertIn("Kuota Gemini", reply)
        assistant.tools.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
