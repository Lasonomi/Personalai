"""Task Service"""
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: UUID, data: TaskCreate) -> Task:
        task = Task(
            user_id=user_id,
            title=data.title,
            description=data.description,
            category=data.category,
            priority=data.priority,
            deadline=data.deadline,
            estimated_duration=data.estimated_duration,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_by_id(self, user_id: UUID, task_id: UUID) -> Optional[Task]:
        result = await self.db.execute(
            select(Task).where(and_(Task.id == task_id, Task.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        user_id: UUID,
        status: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> List[Task]:
        query = select(Task).where(Task.user_id == user_id)
        if status:
            query = query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
        query = query.order_by(Task.deadline.nulls_last())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def complete(self, user_id: UUID, task_id: UUID) -> Optional[Task]:
        task = await self.get_by_id(user_id, task_id)
        if not task:
            return None
        task.status = "COMPLETED"
        task.completed_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update(self, user_id: UUID, task_id: UUID, data: TaskUpdate) -> Optional[Task]:
        task = await self.get_by_id(user_id, task_id)
        if not task:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def delete(self, user_id: UUID, task_id: UUID) -> bool:
        task = await self.get_by_id(user_id, task_id)
        if not task:
            return False
        await self.db.delete(task)
        await self.db.commit()
        return True
