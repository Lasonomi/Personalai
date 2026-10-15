from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.ai.orchestrator import AIOrchestrator


class RecordingTools:
    def __init__(self):
        self.calls = []

    async def execute(self, name, args, user_id):
        self.calls.append((name, args, user_id))
        if name == "create_event":
            return {
                "success": True,
                "id": "event-1",
                "title": args["title"],
                "conflicts": [],
            }
        return {"success": True, "title": args.get("title", "")}


class OrchestratorP0Tests(IsolatedAsyncioTestCase):
    async def test_schedule_includes_pending_reminders_and_events_in_time_order(self):
        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        tools = RecordingTools()

        async def execute(name, args, user_id):
            tools.calls.append((name, args, user_id))
            if name == "get_events":
                return {
                    "success": True,
                    "events": [
                        {
                            "title": "Kuliah",
                            "start_at": "2026-10-07T09:00:00+07:00",
                        }
                    ],
                }
            if name == "get_reminders":
                return {
                    "success": True,
                    "reminders": [
                        {
                            "title": "Voli",
                            "remind_at": "2026-10-07T03:00:00",
                        }
                    ],
                }
            self.fail(f"Unexpected tool call: {name}")

        tools.execute = execute
        orchestrator = AIOrchestrator()
        orchestrator.tools = tools
        with patch.object(
            orchestrator,
            "_now",
            return_value=datetime.fromisoformat("2026-10-07T08:00:00+07:00"),
        ):
            reply = await orchestrator._get_schedule("hari ini ada apa", user)

        self.assertIn("09:00 — Event: Kuliah", reply)
        self.assertIn("10:00 — Pengingat: Voli", reply)
        self.assertLess(reply.index("Kuliah"), reply.index("Voli"))
        self.assertEqual([call[0] for call in tools.calls], ["get_events", "get_reminders"])

    async def test_process_creates_event_with_explicit_date_and_persists_chat(self):
        user = SimpleNamespace(
            id=uuid4(),
            timezone="Asia/Jakarta",
        )
        conversation = SimpleNamespace(id=uuid4())
        tools = RecordingTools()
        orchestrator = AIOrchestrator()
        orchestrator.tools = tools

        with (
            patch(
                "app.ai.orchestrator.store_service.get_or_create_user",
                new=AsyncMock(return_value=user),
            ),
            patch(
                "app.ai.orchestrator.store_service.get_or_create_conversation",
                new=AsyncMock(return_value=conversation),
            ),
            patch(
                "app.ai.orchestrator.store_service.get_conversation_history",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.ai.orchestrator.store_service.save_message",
                new=AsyncMock(),
            ) as save_message,
        ):
            reply = await orchestrator.process(
                "Besok jam 8 aku ada kuliah",
                "discord",
                platform_user_id="1234",
                platform_chat_id="5678",
            )

        self.assertIn("kuliah", reply)
        self.assertEqual(tools.calls[0][0], "create_event")
        self.assertEqual(tools.calls[0][1]["title"], "kuliah")
        start_at = datetime.fromisoformat(tools.calls[0][1]["start_at"])
        self.assertEqual(start_at.utcoffset().total_seconds(), 7 * 60 * 60)
        self.assertEqual(start_at.hour, 8)
        self.assertEqual(save_message.await_count, 2)

    async def test_event_without_explicit_date_asks_instead_of_guessing(self):
        orchestrator = AIOrchestrator()
        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        reply = await orchestrator._create_event(
            "kuliah jam 8", user, "discord", "1234", "discord:1234"
        )
        self.assertIn("Kapan", reply)
        self.assertIn("discord:1234", orchestrator._pending_clarifications)

    async def test_detect_intent_is_callable_on_an_orchestrator_instance(self):
        orchestrator = AIOrchestrator()

        self.assertEqual(orchestrator.detect_intent("hari ini ada apa"), "GET_EVENTS")
        self.assertEqual(
            orchestrator.detect_intent("cari informasi tentang cuaca Jakarta"),
            "SEARCH_WEB",
        )
        self.assertEqual(
            orchestrator.detect_intent(
                "Indonesia memperingati Hari Kartini setiap tanggal berapa?"
            ),
            "SEARCH_WEB",
        )
        self.assertEqual(orchestrator.detect_intent("Sekarang tanggal berapa?"), "GET_TIME")
        self.assertEqual(orchestrator.detect_intent("hari ini hari apa?"), "GET_TIME")
        self.assertEqual(orchestrator.detect_intent("Jam berapa?"), "GET_TIME")

    async def test_historical_date_question_searches_instead_of_returning_current_time(self):
        class SearchTools:
            def __init__(self):
                self.calls = []

            async def execute(self, name, args, _user_id):
                self.calls.append((name, args))
                return {
                    "success": True,
                    "query": args["query"],
                    "answer": "",
                    "results": [
                        {
                            "title": "Hari Kartini",
                            "url": "https://example.test/kartini",
                            "snippet": "Hari Kartini diperingati setiap tanggal 21 April.",
                        }
                    ],
                }

        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        orchestrator = AIOrchestrator()
        orchestrator.tools = SearchTools()

        reply = await orchestrator._handle_message(
            "Indonesia memperingati Hari Kartini setiap tanggal berapa?",
            "discord",
            "1234",
            user,
            [],
            "discord:1234",
        )

        self.assertIn("21 April", reply)
        self.assertNotIn("Sekarang", reply)
        self.assertEqual(orchestrator.tools.calls[0][0], "search_web")

    async def test_search_uses_engine_by_default_and_ai_only_when_requested(self):
        class SearchTools:
            def __init__(self):
                self.calls = []

            async def execute(self, name, args, user_id):
                self.calls.append((name, args, user_id))
                return {
                    "success": True,
                    "query": args["query"],
                    "answer": "",
                    "results": [
                        {
                            "title": "Cuaca Jakarta",
                            "url": "https://example.test/weather",
                            "snippet": "Prakiraan cuaca terbaru.",
                        }
                    ],
                }

        class SearchAI:
            is_configured = True

            def __init__(self):
                self.calls = []

            async def chat(self, **kwargs):
                self.calls.append(kwargs)
                return {"content": "Ringkasan AI berbasis sumber."}

        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        orchestrator = AIOrchestrator()
        orchestrator.tools = SearchTools()
        orchestrator.ai = SearchAI()

        search_reply = await orchestrator._handle_search(
            "cari informasi tentang cuaca Jakarta", user
        )

        self.assertIn("Cuaca Jakarta", search_reply)
        self.assertNotIn("Jawaban AI", search_reply)
        self.assertEqual(orchestrator.tools.calls[0][1]["query"], "cuaca Jakarta")
        self.assertEqual(orchestrator.ai.calls, [])

        ai_reply = await orchestrator._handle_search(
            "pake AI untuk search cuaca Jakarta", user
        )

        self.assertIn("Ringkasan AI berbasis sumber.", ai_reply)
        self.assertEqual(orchestrator.tools.calls[1][1]["query"], "cuaca Jakarta")
        self.assertEqual(len(orchestrator.ai.calls), 1)

    async def test_memory_delete_requires_specificity_and_confirmation(self):
        orchestrator = AIOrchestrator()
        user = SimpleNamespace(id=uuid4(), timezone="Asia/Jakarta")
        unclear = await orchestrator._try_rule_based(
            "DELETE_MEMORY", "hapus memory", user, "discord", "1234", "discord:1234"
        )
        self.assertIn("Memory mana", unclear)
        self.assertNotIn("discord:1234", orchestrator._pending_actions)

        prompt = await orchestrator._try_rule_based(
            "DELETE_MEMORY",
            "hapus memory tentang pola tidur",
            user,
            "discord",
            "1234",
            "discord:1234",
        )
        self.assertIn("pola tidur", prompt)
        self.assertEqual(
            orchestrator._pending_actions["discord:1234"]["arguments"],
            {"query": "pola tidur"},
        )
