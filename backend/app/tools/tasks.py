"""Task tools backed by persistent, user-scoped task records."""
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models.task import Task

TASK_STATUSES = {"TODO", "IN_PROGRESS", "COMPLETED", "OVERDUE", "CANCELLED"}
TASK_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}


def _user_id(value: str) -> UUID:
    return UUID(str(value))


def _datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize(task: Task) -> Dict[str, Any]:
    status = task.status
    if (
        task.deadline
        and task.deadline < datetime.now(timezone.utc).replace(tzinfo=None)
        and status in {"TODO", "IN_PROGRESS"}
    ):
        status = "OVERDUE"
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description,
        "category": task.category,
        "priority": task.priority,
        "deadline": task.deadline.isoformat() if task.deadline else None,
        "status": status,
        "estimated_duration": task.estimated_duration,
    }


async def create_task(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        raise ValueError("Judul task wajib diisi.")
    priority = str(args.get("priority", "MEDIUM")).upper()
    if priority not in TASK_PRIORITIES:
        raise ValueError("Priority harus LOW, MEDIUM, HIGH, atau URGENT.")
    async with AsyncSessionLocal() as db:
        task = Task(
            user_id=_user_id(user_id),
            title=title[:255],
            description=args.get("description"),
            category=str(args.get("category", "OTHER")).upper(),
            priority=priority,
            deadline=_datetime(args.get("deadline")),
            status="TODO",
            estimated_duration=args.get("estimated_duration"),
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return _serialize(task)


async def get_tasks(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    query = select(Task).where(Task.user_id == _user_id(user_id))
    if args.get("status"):
        query = query.where(Task.status == str(args["status"]).upper())
    if args.get("priority"):
        query = query.where(Task.priority == str(args["priority"]).upper())
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            query.order_by(Task.deadline.is_(None), Task.deadline, Task.created_at.desc()).limit(50)
        )
        tasks = [_serialize(task) for task in result.scalars().all()]
    return {"tasks": tasks, "count": len(tasks)}


async def update_task(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    task_id = UUID(str(args.get("task_id", "")))
    allowed = {"title", "description", "category", "priority", "deadline", "status", "estimated_duration"}
    updates = {key: value for key, value in args.items() if key in allowed and value is not None}
    if "priority" in updates:
        updates["priority"] = str(updates["priority"]).upper()
        if updates["priority"] not in TASK_PRIORITIES:
            raise ValueError("Priority harus LOW, MEDIUM, HIGH, atau URGENT.")
    if "status" in updates:
        updates["status"] = str(updates["status"]).upper()
        if updates["status"] not in TASK_STATUSES:
            raise ValueError("Status task tidak valid.")
    if "deadline" in updates:
        updates["deadline"] = _datetime(updates["deadline"])
    async with AsyncSessionLocal() as db:
        task = await db.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == _user_id(user_id))
        )
        if not task:
            return {"success": False, "error": "Task tidak ditemukan."}
        for key, value in updates.items():
            setattr(task, key, value)
        if task.status == "COMPLETED" and task.completed_at is None:
            task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        elif task.status != "COMPLETED":
            task.completed_at = None
        await db.commit()
        await db.refresh(task)
        return _serialize(task)


async def complete_task(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    task_id = UUID(str(args.get("task_id", "")))
    async with AsyncSessionLocal() as db:
        task = await db.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == _user_id(user_id))
        )
        if not task:
            return {"success": False, "error": "Task tidak ditemukan."}
        task.status = "COMPLETED"
        task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await db.commit()
        await db.refresh(task)
        return _serialize(task)


async def delete_task(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    task_id = UUID(str(args.get("task_id", "")))
    async with AsyncSessionLocal() as db:
        task = await db.scalar(
            select(Task).where(Task.id == task_id, Task.user_id == _user_id(user_id))
        )
        if not task:
            return {"success": False, "error": "Task tidak ditemukan."}
        task.status = "CANCELLED"
        await db.commit()
        return {"success": True, "id": str(task.id), "status": task.status}
