"""
Tool Registry — AI only interacts with the system through tools.
"""
from typing import Any, Callable, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, func: Callable, schema: Optional[Dict[str, Any]] = None):
        self._tools[name] = func
        if schema:
            self._schemas[name] = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
        logger.info(f"Tool registered: {name}")

    def get(self, name: str) -> Optional[Callable]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def definitions(self) -> list[Dict[str, Any]]:
        return list(self._schemas.values())

    async def execute(self, name: str, args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' not found"}
        try:
            result = await tool(args=args, user_id=user_id)
            if isinstance(result, dict) and result.get("success") is False:
                return {"success": False, "tool": name, **result}
            if isinstance(result, dict):
                return {"success": True, "tool": name, **result}
            return {"success": True, "tool": name, "result": result}
        except ValueError as e:
            return {"success": False, "tool": name, "error": str(e)}
        except Exception:
            logger.exception(f"Tool {name} failed")
            return {
                "success": False,
                "tool": name,
                "error": "Terjadi kesalahan internal saat menjalankan tool.",
            }


# Global registry instance
tool_registry = ToolRegistry()

def _schema(description: str, properties: Dict[str, Any], required: Optional[list[str]] = None):
    return {
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
    }


STRING = {"type": "string"}
DATETIME = {
    "type": "string",
    "description": "ISO-8601 datetime including timezone offset, e.g. 2026-10-08T08:00:00+07:00.",
}
EVENT_ID = {"type": "string", "description": "ID from a previously returned event."}
TASK_ID = {"type": "string", "description": "ID from a previously returned task."}
REMINDER_ID = {"type": "string", "description": "ID from a previously returned reminder."}
MEMORY_ID = {"type": "string", "description": "ID from a previously returned memory."}


def register_default_tools(registry: ToolRegistry | None = None):
    """Register all available tools."""
    from app.tools import calendar, tasks, reminders, memory, search, documents, notes, quiz
    target = registry or tool_registry

    definitions = {
        "create_event": (
            calendar.create_event,
            _schema(
                "Create an event only when its date and start time are clear. Return conflicts so the assistant can warn the user.",
                {
                    "title": STRING,
                    "start_at": DATETIME,
                    "end_at": DATETIME,
                    "description": STRING,
                    "category": STRING,
                    "location": STRING,
                    "recurrence": STRING,
                },
                ["title", "start_at"],
            ),
        ),
        "get_events": (
            calendar.get_events,
            _schema(
                "List the current user's events. Use ISO-8601 bounds when the user asks about a date range.",
                {"date_from": DATETIME, "date_to": DATETIME, "category": STRING},
            ),
        ),
        "update_event": (
            calendar.update_event,
            _schema(
                "Update a specific event using its ID from get_events.",
                {
                    "event_id": EVENT_ID,
                    "title": STRING,
                    "start_at": DATETIME,
                    "end_at": DATETIME,
                    "description": STRING,
                    "category": STRING,
                    "location": STRING,
                    "recurrence": STRING,
                },
                ["event_id"],
            ),
        ),
        "delete_event": (
            calendar.delete_event,
            _schema("Cancel an event using its ID from get_events.", {"event_id": EVENT_ID}, ["event_id"]),
        ),
        "check_conflict": (
            calendar.check_conflict,
            _schema("Check for overlapping events before proposing a schedule.", {"start_at": DATETIME, "end_at": DATETIME}, ["start_at"]),
        ),
        "create_task": (
            tasks.create_task,
            _schema(
                "Create a task with an optional deadline and priority.",
                {
                    "title": STRING,
                    "description": STRING,
                    "category": STRING,
                    "deadline": DATETIME,
                    "priority": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "URGENT"]},
                    "estimated_duration": {"type": "integer", "minimum": 1},
                },
                ["title"],
            ),
        ),
        "get_tasks": (
            tasks.get_tasks,
            _schema("List the current user's tasks.", {"status": STRING, "priority": STRING}),
        ),
        "update_task": (
            tasks.update_task,
            _schema(
                "Update one task using its ID from get_tasks.",
                {
                    "task_id": TASK_ID,
                    "title": STRING,
                    "description": STRING,
                    "category": STRING,
                    "priority": STRING,
                    "deadline": DATETIME,
                    "status": STRING,
                    "estimated_duration": {"type": "integer", "minimum": 1},
                },
                ["task_id"],
            ),
        ),
        "complete_task": (
            tasks.complete_task,
            _schema("Mark a task completed using its ID from get_tasks.", {"task_id": TASK_ID}, ["task_id"]),
        ),
        "delete_task": (
            tasks.delete_task,
            _schema("Cancel a task using its ID from get_tasks.", {"task_id": TASK_ID}, ["task_id"]),
        ),
        "create_reminder": (
            reminders.create_reminder,
            _schema(
                "Schedule a reminder. The reminder time must be a future ISO-8601 datetime with timezone offset.",
                {
                    "title": STRING,
                    "remind_at": DATETIME,
                    "event_id": EVENT_ID,
                    "task_id": TASK_ID,
                    "delivery_platform": STRING,
                    "delivery_user_id": STRING,
                },
                ["title", "remind_at"],
            ),
        ),
        "get_reminders": (
            reminders.get_reminders,
            _schema(
                "List reminders for the current user, optionally filtered by status and an ISO-8601 time range.",
                {"status": STRING, "date_from": DATETIME, "date_to": DATETIME},
            ),
        ),
        "update_reminder": (
            reminders.update_reminder,
            _schema(
                "Reschedule or rename a pending reminder using its ID.",
                {"reminder_id": REMINDER_ID, "title": STRING, "remind_at": DATETIME},
                ["reminder_id"],
            ),
        ),
        "delete_reminder": (
            reminders.delete_reminder,
            _schema("Cancel a reminder using its ID from get_reminders.", {"reminder_id": REMINDER_ID}, ["reminder_id"]),
        ),
        "save_memory": (
            memory.save_memory,
            _schema(
                "Save durable personal information only when the user explicitly asks you to remember it.",
                {"content": STRING, "category": STRING, "importance": {"type": "number", "minimum": 0, "maximum": 1}},
                ["content"],
            ),
        ),
        "get_memory": (
            memory.get_memory,
            _schema("Retrieve the current user's memories.", {"query": STRING, "category": STRING}),
        ),
        "update_memory": (
            memory.update_memory,
            _schema(
                "Update a memory using its ID from get_memory.",
                {"memory_id": MEMORY_ID, "content": STRING, "category": STRING},
                ["memory_id", "content"],
            ),
        ),
        "delete_memory": (
            memory.delete_memory,
            _schema(
                "Delete a specific memory by ID or matching query. Only use all=true when the user explicitly requests deletion of all memories.",
                {"memory_id": MEMORY_ID, "query": STRING, "all": {"type": "boolean"}},
            ),
        ),
    }

    for name, (function, schema) in definitions.items():
        target.register(name, function, schema)

    target.register(
        "search_web",
        search.search_web,
        _schema(
            "Search the web for current or specific facts, weather, news, and other information that needs reliable sources. Use when the answer may have changed or is not confidently known. If a location is needed and missing, ask the user before searching.",
            {
                "query": STRING,
                "max_results": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            ["query"],
        ),
    )
    # These integrations are not yet implemented and are not exposed as successful placeholder actions.
    target.register("search_documents", documents.search_documents)
    target.register("create_note", notes.create_note)
    target.register("search_notes", notes.search_notes)
    target.register("generate_quiz", quiz.generate_quiz)


def create_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_default_tools(registry)
    return registry
