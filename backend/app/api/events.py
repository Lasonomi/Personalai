"""Events API"""
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.database.models.user import User
from app.schemas.event import EventCreate, EventUpdate, EventResponse
from app.services.event_service import EventService

router = APIRouter()


@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    data: EventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = EventService(db)
    event = await service.create(current_user.id, data)
    return event


@router.get("/", response_model=List[EventResponse])
async def list_events(
    current_user: User = Depends(get_current_user),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    service = EventService(db)
    return await service.list(current_user.id, date_from, date_to, category)


@router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = EventService(db)
    event = await service.get_by_id(current_user.id, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.patch("/{event_id}", response_model=EventResponse)
async def update_event(
    event_id: UUID,
    data: EventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = EventService(db)
    event = await service.update(current_user.id, event_id, data)
    if not event:
        raise HTTPException(404, "Event not found")
    return event


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = EventService(db)
    ok = await service.delete(current_user.id, event_id)
    if not ok:
        raise HTTPException(404, "Event not found")
