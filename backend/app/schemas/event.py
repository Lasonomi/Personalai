from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class EventCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: Optional[datetime] = None
    description: Optional[str] = None
    category: str = "OTHER"
    location: Optional[str] = None
    recurrence: Optional[str] = None
    notes: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    description: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    recurrence: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class EventResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: Optional[str]
    category: str
    start_at: datetime
    end_at: Optional[datetime]
    location: Optional[str]
    recurrence: Optional[str]
    status: str
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
