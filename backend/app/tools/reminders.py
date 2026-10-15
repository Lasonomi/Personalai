"""Reminder tools backed by persistent, user-scoped reminder records."""
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models.event import Event
from app.database.models.reminder import Reminder
from app.database.models.task import Task


def _user_id(value: str) -> UUID:
    return UUID(str(value))


def _datetime(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize(reminder: Reminder) -> Dict[str, Any]:
    return {
        "id": str(reminder.id),
        "title": reminder.title,
        "remind_at": reminder.remind_at.isoformat(),
        "event_id": str(reminder.event_id) if reminder.event_id else None,
        "task_id": str(reminder.task_id) if reminder.task_id else None,
        "delivery_platform": reminder.delivery_platform,
        "delivery_user_id": reminder.delivery_user_id,
        "status": reminder.status,
    }


async def create_reminder(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        raise ValueError("Isi reminder wajib diisi.")
    owner_id = _user_id(user_id)
    event_id = UUID(str(args["event_id"])) if args.get("event_id") else None
    task_id = UUID(str(args["task_id"])) if args.get("task_id") else None
    remind_at = _datetime(args.get("remind_at"))
    if remind_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError("Waktu reminder harus di masa depan.")

    async with AsyncSessionLocal() as db:
        if event_id and not await db.scalar(
            select(Event.id).where(Event.id == event_id, Event.user_id == owner_id)
        ):
            raise ValueError("Event reminder tidak ditemukan.")
        if task_id and not await db.scalar(
            select(Task.id).where(Task.id == task_id, Task.user_id == owner_id)
        ):
            raise ValueError("Task reminder tidak ditemukan.")
        reminder = Reminder(
            user_id=owner_id,
            title=title[:255],
            remind_at=remind_at,
            event_id=event_id,
            task_id=task_id,
            delivery_platform=args.get("delivery_platform"),
            delivery_user_id=str(args["delivery_user_id"]) if args.get("delivery_user_id") else None,
            status="PENDING",
        )
        db.add(reminder)
        await db.commit()
        await db.refresh(reminder)
        return _serialize(reminder)


async def get_reminders(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    query = select(Reminder).where(Reminder.user_id == _user_id(user_id))
    if args.get("status"):
        query = query.where(Reminder.status == str(args["status"]).upper())
    if args.get("date_from"):
        query = query.where(Reminder.remind_at >= _datetime(args["date_from"]))
    if args.get("date_to"):
        query = query.where(Reminder.remind_at < _datetime(args["date_to"]))
    async with AsyncSessionLocal() as db:
        result = await db.execute(query.order_by(Reminder.remind_at).limit(50))
        reminders = [_serialize(item) for item in result.scalars().all()]
    return {"reminders": reminders, "count": len(reminders)}


async def update_reminder(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    reminder_id = UUID(str(args.get("reminder_id", "")))
    updates: dict[str, Any] = {}
    if args.get("title") is not None:
        updates["title"] = str(args["title"]).strip()[:255]
    if args.get("remind_at") is not None:
        updates["remind_at"] = _datetime(args["remind_at"])
        if updates["remind_at"] <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise ValueError("Waktu reminder harus di masa depan.")
    async with AsyncSessionLocal() as db:
        reminder = await db.scalar(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == _user_id(user_id),
                Reminder.status == "PENDING",
            )
        )
        if not reminder:
            return {"success": False, "error": "Reminder aktif tidak ditemukan."}
        for key, value in updates.items():
            setattr(reminder, key, value)
        await db.commit()
        await db.refresh(reminder)
        return _serialize(reminder)


async def delete_reminder(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    reminder_id = UUID(str(args.get("reminder_id", "")))
    async with AsyncSessionLocal() as db:
        reminder = await db.scalar(
            select(Reminder).where(
                Reminder.id == reminder_id,
                Reminder.user_id == _user_id(user_id),
                Reminder.status == "PENDING",
            )
        )
        if not reminder:
            return {"success": False, "error": "Reminder aktif tidak ditemukan."}
        reminder.status = "CANCELLED"
        await db.commit()
        return {"success": True, "id": str(reminder.id), "status": reminder.status}
