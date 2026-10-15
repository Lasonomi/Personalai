from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class MemoryCreate(BaseModel):
    content: str
    category: str = "OTHER"
    importance: float = 0.5


class MemoryResponse(BaseModel):
    id: UUID
    user_id: UUID
    content: str
    category: str
    importance: float
    created_at: datetime

    class Config:
        from_attributes = True
