from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "OTHER"
    priority: str = "MEDIUM"
    deadline: Optional[datetime] = None
    estimated_duration: Optional[int] = None  # minutes


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    deadline: Optional[datetime] = None
    status: Optional[str] = None
    estimated_duration: Optional[int] = None


class TaskResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    description: Optional[str]
    category: str
    priority: str
    deadline: Optional[datetime]
    status: str
    estimated_duration: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
