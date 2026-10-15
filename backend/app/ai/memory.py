"""
Memory Service
"""
from enum import Enum
from typing import List, Optional


class MemoryCategory(str, Enum):
    PROFILE = "PROFILE"
    ACADEMIC = "ACADEMIC"
    PREFERENCE = "PREFERENCE"
    PERSONAL = "PERSONAL"
    WORK = "WORK"
    LEARNING = "LEARNING"
    TASK = "TASK"
    GOAL = "GOAL"
    RELATIONSHIP = "RELATIONSHIP"
    OTHER = "OTHER"


class MemoryService:
    async def save(self, user_id: str, content: str, category: str = "OTHER", importance: float = 0.5):
        raise NotImplementedError

    async def get(self, user_id: str, query: Optional[str] = None, category: Optional[str] = None) -> List[dict]:
        raise NotImplementedError

    async def delete(self, user_id: str, memory_id: Optional[str] = None, all: bool = False):
        raise NotImplementedError
