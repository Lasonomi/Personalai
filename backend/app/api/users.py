"""Users API"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database.connection import get_db
from app.database.models.user import User
from app.schemas.user import UserUpdate, UserResponse
from app.services.user_service import UserService

router = APIRouter()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(403, "You may only access your own profile.")
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user_id != current_user.id:
        raise HTTPException(403, "You may only update your own profile.")
    service = UserService(db)
    user = await service.update(user_id, data)
    if not user:
        raise HTTPException(404, "User not found")
    return user

