"""Authenticated reminder CRUD API."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.database.models.event import Event
from app.database.models.reminder import Reminder
from app.database.models.task import Task
from app.database.models.user import PlatformAccount, User
from app.schemas.reminder import ReminderCreate, ReminderResponse, ReminderUpdate

router = APIRouter()
REMINDER_STATUSES = {"PENDING", "SENDING", "SENT", "CANCELLED"}


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.post("/", response_model=ReminderResponse, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    data: ReminderCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    remind_at = _utc_naive(data.remind_at)
    if remind_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(422, "Waktu reminder harus berada di masa depan.")
    account = await db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.user_id == current_user.id)
        .order_by(PlatformAccount.linked_at.desc())
        .limit(1)
    )
    if not account:
        raise HTTPException(409, "Hubungkan akun Telegram atau Discord untuk menerima reminder.")
    if data.event_id and not await db.scalar(
        select(Event.id).where(
            Event.id == data.event_id,
            Event.user_id == current_user.id,
            Event.status == "ACTIVE",
        )
    ):
        raise HTTPException(404, "Event tidak ditemukan.")
    if data.task_id and not await db.scalar(
        select(Task.id).where(Task.id == data.task_id, Task.user_id == current_user.id)
    ):
        raise HTTPException(404, "Task tidak ditemukan.")
    reminder = Reminder(
        user_id=current_user.id,
        event_id=data.event_id,
        task_id=data.task_id,
        title=data.title.strip(),
        remind_at=remind_at,
        delivery_platform=account.platform,
        delivery_user_id=account.platform_user_id,
        status="PENDING",
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.get("/", response_model=list[ReminderResponse])
async def list_reminders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    reminder_status: str | None = Query(default=None, alias="status"),
):
    query = select(Reminder).where(Reminder.user_id == current_user.id)
    if reminder_status:
        normalized = reminder_status.upper()
        if normalized not in REMINDER_STATUSES:
            raise HTTPException(422, "Status reminder tidak valid.")
        query = query.where(Reminder.status == normalized)
    rows = await db.execute(query.order_by(Reminder.remind_at).limit(100))
    return list(rows.scalars().all())


@router.patch("/{reminder_id}", response_model=ReminderResponse)
async def update_reminder(
    reminder_id: UUID,
    data: ReminderUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    reminder = await db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == current_user.id,
            Reminder.status == "PENDING",
        )
    )
    if not reminder:
        raise HTTPException(404, "Reminder aktif tidak ditemukan.")
    updates = data.model_dump(exclude_unset=True)
    if "title" in updates and updates["title"] is not None:
        reminder.title = updates["title"].strip()
    if updates.get("remind_at") is not None:
        remind_at = _utc_naive(updates["remind_at"])
        if remind_at <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(422, "Waktu reminder harus berada di masa depan.")
        reminder.remind_at = remind_at
        reminder.next_attempt_at = None
    await db.commit()
    await db.refresh(reminder)
    return reminder


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reminder(
    reminder_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    reminder = await db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == current_user.id,
            Reminder.status == "PENDING",
        )
    )
    if not reminder:
        raise HTTPException(404, "Reminder aktif tidak ditemukan.")
    reminder.status = "CANCELLED"
    reminder.claimed_at = None
    await db.commit()
    return None
