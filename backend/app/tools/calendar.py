"""Calendar tools backed by the user's persistent event records."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.database.connection import AsyncSessionLocal
from app.database.models.event import Event
from app.database.models.user import User


def _user_id(value: str) -> UUID:
    return UUID(str(value))


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Tanggal dan waktu wajib diisi dalam format ISO-8601.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _serialize(event: Event) -> Dict[str, Any]:
    return {
        "id": str(event.id),
        "title": event.title,
        "description": event.description,
        "category": event.category,
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "location": event.location,
        "recurrence": event.recurrence,
        "status": event.status,
    }


async def create_event(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    title = str(args.get("title", "")).strip()
    if not title:
        raise ValueError("Judul event wajib diisi.")
    start_at = _datetime(args.get("start_at"))
    end_at = _datetime(args["end_at"]) if args.get("end_at") else None
    if end_at and end_at <= start_at:
        raise ValueError("Waktu selesai harus setelah waktu mulai.")
    owner_id = _user_id(user_id)

    async with AsyncSessionLocal() as db:
        event = Event(
            user_id=owner_id,
            title=title[:255],
            description=args.get("description"),
            category=str(args.get("category", "OTHER")).upper(),
            start_at=start_at,
            end_at=end_at,
            location=args.get("location"),
            recurrence=args.get("recurrence"),
            status="ACTIVE",
        )
        db.add(event)
        await db.flush()
        conflicts = await _find_conflicts(db, owner_id, start_at, end_at, exclude_id=event.id)
        await db.commit()
        await db.refresh(event)
        result = _serialize(event)
        result["conflicts"] = [_serialize(item) for item in conflicts]
        return result


async def _find_conflicts(
    db,
    owner_id: UUID,
    start_at: datetime,
    end_at: datetime | None,
    exclude_id: UUID | None = None,
) -> list[Event]:
    proposed_end = end_at or (start_at + timedelta(hours=1))
    conditions = [
        Event.user_id == owner_id,
        Event.status == "ACTIVE",
        Event.start_at < proposed_end,
        or_(
            Event.end_at > start_at,
            and_(
                Event.end_at.is_(None),
                Event.start_at > start_at - timedelta(hours=1),
            ),
        ),
    ]
    if exclude_id:
        conditions.append(Event.id != exclude_id)
    result = await db.execute(
        select(Event).where(and_(*conditions)).order_by(Event.start_at).limit(10)
    )
    return list(result.scalars().all())


async def get_events(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    owner_id = _user_id(user_id)
    date_from = _datetime(args["date_from"]) if args.get("date_from") else None
    date_to = _datetime(args["date_to"]) if args.get("date_to") else None
    query = select(Event).where(Event.user_id == owner_id, Event.status == "ACTIVE")
    if date_to:
        query = query.where(Event.start_at < date_to)
    if date_from:
        query = query.where(
            or_(Event.start_at >= date_from, Event.recurrence.is_not(None))
        )
    if args.get("category"):
        query = query.where(Event.category == str(args["category"]).upper())

    async with AsyncSessionLocal() as db:
        result = await db.execute(query.order_by(Event.start_at).limit(50))
        events = list(result.scalars().all())
        user = await db.get(User, owner_id)
        timezone_name = user.timezone if user else "UTC"
    serialized: list[Dict[str, Any]] = []
    if date_from and date_to:
        for event in events:
            occurrences = _event_occurrences(event, date_from, date_to, timezone_name)
            serialized.extend(occurrences)
    else:
        serialized = [_serialize(event) for event in events]
    serialized.sort(key=lambda event: event.get("start_at") or "")
    serialized = serialized[:50]
    return {"events": serialized, "count": len(serialized)}


def _event_occurrences(
    event: Event, date_from: datetime, date_to: datetime, timezone_name: str
) -> list[Dict[str, Any]]:
    base = event.start_at.replace(tzinfo=timezone.utc).astimezone(
        _timezone(timezone_name)
    )
    local_from = date_from.replace(tzinfo=timezone.utc).astimezone(
        _timezone(timezone_name)
    )
    local_to = date_to.replace(tzinfo=timezone.utc).astimezone(
        _timezone(timezone_name)
    )
    recurrence = (event.recurrence or "").upper()
    step_days: int | None = None
    target_weekday: int | None = None
    if recurrence == "DAILY":
        step_days = 1
    elif recurrence.startswith("WEEKLY:"):
        value = recurrence.split(":", 1)[1]
        weekdays = {
            "MONDAY": 0, "TUESDAY": 1, "WEDNESDAY": 2, "THURSDAY": 3,
            "FRIDAY": 4, "SATURDAY": 5, "SUNDAY": 6,
        }
        try:
            target_weekday = int(value)
        except ValueError:
            target_weekday = weekdays.get(value)
        if target_weekday is not None and 0 <= target_weekday <= 6:
            step_days = 7
    if step_days is None:
        occurrence = base
        if occurrence < local_from or occurrence > local_to:
            return []
        serialized = _serialize(event)
        serialized["start_at"] = occurrence.astimezone(timezone.utc).isoformat()
        return [serialized]

    if step_days == 7:
        delta = (target_weekday - base.weekday()) % 7
        first = base + timedelta(days=delta)
        if first < base:
            first += timedelta(days=7)
    else:
        first = base
    while first < local_from:
        first += timedelta(days=step_days)

    results: list[Dict[str, Any]] = []
    duration = event.end_at - event.start_at if event.end_at else None
    while first <= local_to and len(results) < 50:
        start_utc = first.astimezone(timezone.utc)
        if date_from <= start_utc.replace(tzinfo=None) < date_to:
            serialized = _serialize(event)
            serialized["start_at"] = start_utc.isoformat()
            if duration:
                serialized["end_at"] = (start_utc + duration).isoformat()
            results.append(serialized)
        first += timedelta(days=step_days)
    return results


def _timezone(name: str):
    from zoneinfo import ZoneInfo
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


async def update_event(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    event_id = UUID(str(args.get("event_id", "")))
    owner_id = _user_id(user_id)
    allowed = {"title", "description", "category", "start_at", "end_at", "location", "recurrence"}
    updates = {key: value for key, value in args.items() if key in allowed and value is not None}
    if "start_at" in updates:
        updates["start_at"] = _datetime(updates["start_at"])
    if "end_at" in updates:
        updates["end_at"] = _datetime(updates["end_at"])
    if "category" in updates:
        updates["category"] = str(updates["category"]).upper()

    async with AsyncSessionLocal() as db:
        event = await db.scalar(
            select(Event).where(Event.id == event_id, Event.user_id == owner_id)
        )
        if not event:
            return {"success": False, "error": "Event tidak ditemukan."}
        for key, value in updates.items():
            setattr(event, key, value)
        if event.end_at and event.end_at <= event.start_at:
            raise ValueError("Waktu selesai harus setelah waktu mulai.")
        conflicts = await _find_conflicts(
            db, owner_id, event.start_at, event.end_at, exclude_id=event.id
        )
        await db.commit()
        await db.refresh(event)
        result = _serialize(event)
        result["conflicts"] = [_serialize(item) for item in conflicts]
        return result


async def delete_event(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    event_id = UUID(str(args.get("event_id", "")))
    async with AsyncSessionLocal() as db:
        event = await db.scalar(
            select(Event).where(Event.id == event_id, Event.user_id == _user_id(user_id))
        )
        if not event:
            return {"success": False, "error": "Event tidak ditemukan."}
        event.status = "CANCELLED"
        await db.commit()
        return {"success": True, "id": str(event.id), "status": event.status}


async def check_conflict(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    start_at = _datetime(args.get("start_at"))
    end_at = _datetime(args["end_at"]) if args.get("end_at") else None
    async with AsyncSessionLocal() as db:
        conflicts = await _find_conflicts(db, _user_id(user_id), start_at, end_at)
    return {
        "has_conflict": bool(conflicts),
        "conflicts": [_serialize(event) for event in conflicts],
    }
