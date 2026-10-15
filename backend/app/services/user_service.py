"""User Service"""
from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models.user import User, PlatformAccount
from app.schemas.user import UserCreate, UserUpdate, PlatformLink


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: UserCreate) -> User:
        user = User(
            name=data.name,
            email=data.email,
            timezone=data.timezone,
            language=data.language,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_platform(self, platform: str, platform_user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User)
            .join(PlatformAccount)
            .where(
                PlatformAccount.platform == platform,
                PlatformAccount.platform_user_id == platform_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def link_platform(self, user_id: UUID, data: PlatformLink) -> PlatformAccount:
        account = PlatformAccount(
            user_id=user_id,
            platform=data.platform,
            platform_user_id=data.platform_user_id,
            username=data.username,
        )
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def update(self, user_id: UUID, data: UserUpdate) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.db.commit()
        await self.db.refresh(user)
        return user
