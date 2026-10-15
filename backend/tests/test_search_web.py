import unittest
from unittest.mock import patch

import httpx

from app.tools.registry import create_registry
from app.tools.search import search_web


class TavilySearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_uses_tavily_for_sources_without_generating_an_answer(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "answer": "Hujan diperkirakan malam ini.",
                    "results": [
                        {
                            "title": "Prakiraan cuaca",
                            "url": "https://example.test/weather",
                            "content": "Informasi prakiraan.",
                            "published_date": "2026-10-07",
                        }
                    ],
                },
            )

        def client_factory(**kwargs):
            return async_client_class(
                transport=httpx.MockTransport(handler),
                **kwargs,
            )

        async_client_class = httpx.AsyncClient
        with (
            patch("app.tools.search.settings.TAVILY_API_KEY", "test-tavily-key"),
            patch("app.tools.search.httpx.AsyncClient", side_effect=client_factory),
        ):
            result = await search_web(
                {"query": "weather tonight in Jakarta", "max_results": 3},
                "user-1",
            )

        self.assertEqual(result["provider"], "tavily")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["results"][0]["url"], "https://example.test/weather")
        self.assertEqual(requests[0].url, "https://api.tavily.com/search")
        self.assertIn(
            b'"max_results":3',
            requests[0].content,
        )
        self.assertIn(b'"include_answer":false', requests[0].content)
        self.assertIn(b"test-tavily-key", requests[0].content)

    async def test_missing_key_returns_explicit_not_configured_result(self):
        with patch("app.tools.search.settings.TAVILY_API_KEY", ""):
            result = await search_web({"query": "weather"}, "user-1")

        self.assertFalse(result["success"])
        self.assertIn("TAVILY_API_KEY", result["error"])

    async def test_search_web_is_available_to_the_ai_as_a_tool(self):
        registry = create_registry()
        search_definition = next(
            definition
            for definition in registry.definitions()
            if definition["function"]["name"] == "search_web"
        )

        self.assertIn(
            "query",
            search_definition["function"]["parameters"]["required"],
        )
        self.assertIn(
            "weather",
            search_definition["function"]["description"],
        )


if __name__ == "__main__":
    unittest.main()
