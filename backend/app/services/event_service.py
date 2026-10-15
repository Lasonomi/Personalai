"""Event Service — business logic for calendar"""
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models.event import Event
from app.schemas.event import EventCreate, EventUpdate


class EventService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: UUID, data: EventCreate) -> Event:
        event = Event(
            user_id=user_id,
            title=data.title,
            description=data.description,
            category=data.category,
            start_at=data.start_at,
            end_at=data.end_at,
            location=data.location,
            recurrence=data.recurrence,
            notes=data.notes,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def get_by_id(self, user_id: UUID, event_id: UUID) -> Optional[Event]:
        result = await self.db.execute(
            select(Event).where(and_(Event.id == event_id, Event.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        user_id: UUID,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        category: Optional[str] = None,
    ) -> List[Event]:
        query = select(Event).where(Event.user_id == user_id)
        if date_from:
            query = query.where(Event.start_at >= date_from)
        if date_to:
            query = query.where(Event.start_at <= date_to)
        if category:
            query = query.where(Event.category == category)
        query = query.order_by(Event.start_at)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, user_id: UUID, event_id: UUID, data: EventUpdate) -> Optional[Event]:
        event = await self.get_by_id(user_id, event_id)
        if not event:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(event, field, value)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def delete(self, user_id: UUID, event_id: UUID) -> bool:
        event = await self.get_by_id(user_id, event_id)
        if not event:
            return False
        await self.db.delete(event)
        await self.db.commit()
        return True

    async def check_conflict(
        self, user_id: UUID, start_at: datetime, end_at: Optional[datetime] = None
    ) -> List[Event]:
        end = end_at or start_at
        result = await self.db.execute(
            select(Event).where(
                and_(
                    Event.user_id == user_id,
                    Event.status == "ACTIVE",
                    Event.start_at < end,
                    (Event.end_at >= start_at) | (Event.end_at.is_(None)),
                )
            )
        )
        return list(result.scalars().all())
