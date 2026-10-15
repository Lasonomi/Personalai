"""Memory Service"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, delete

from app.database.models.memory import Memory


class MemoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(
        self,
        user_id: UUID,
        content: str,
        category: str = "OTHER",
        importance: float = 0.5,
    ) -> Memory:
        mem = Memory(
            user_id=user_id,
            content=content,
            category=category,
            importance=importance,
        )
        self.db.add(mem)
        await self.db.commit()
        await self.db.refresh(mem)
        return mem

    async def list(
        self,
        user_id: UUID,
        category: Optional[str] = None,
        limit: int = 50,
    ) -> List[Memory]:
        q = select(Memory).where(Memory.user_id == user_id)
        if category:
            q = q.where(Memory.category == category)
        q = q.order_by(Memory.importance.desc()).limit(limit)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def delete(self, user_id: UUID, memory_id: Optional[UUID] = None, all_: bool = False) -> int:
        if all_:
            result = await self.db.execute(delete(Memory).where(Memory.user_id == user_id))
            await self.db.commit()
            return result.rowcount
        if memory_id:
            result = await self.db.execute(
                delete(Memory).where(and_(Memory.id == memory_id, Memory.user_id == user_id))
            )
            await self.db.commit()
            return result.rowcount
        return 0
