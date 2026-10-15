"""Reminder Service"""
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models.reminder import Reminder


class ReminderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID,
        title: str,
        remind_at: datetime,
        event_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            title=title,
            remind_at=remind_at,
            event_id=event_id,
            task_id=task_id,
        )
        self.db.add(reminder)
        await self.db.commit()
        await self.db.refresh(reminder)
        return reminder

    async def get_due(self, before: datetime) -> List[Reminder]:
        result = await self.db.execute(
            select(Reminder).where(
                and_(
                    Reminder.status == "PENDING",
                    Reminder.remind_at <= before,
                )
            )
        )
        return list(result.scalars().all())

    async def mark_sent(self, reminder_id: UUID) -> None:
        result = await self.db.execute(select(Reminder).where(Reminder.id == reminder_id))
        reminder = result.scalar_one_or_none()
        if reminder:
            reminder.status = "SENT"
            reminder.sent_at = datetime.utcnow()
            await self.db.commit()
