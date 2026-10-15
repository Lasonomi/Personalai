from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import field_validator


class UserCreate(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    timezone: str = "Asia/Jakarta"
    language: str = "id"


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    daily_summary_enabled: Optional[bool] = None
    university: Optional[str] = None
    major: Optional[str] = None
    semester: Optional[str] = None
    preferences: Optional[str] = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError("Zona waktu tidak valid.") from error
        return value


class UserResponse(BaseModel):
    id: UUID
    name: Optional[str]
    email: Optional[str]
    timezone: str
    language: str
    daily_summary_enabled: bool
    university: Optional[str]
    major: Optional[str]
    semester: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PlatformLink(BaseModel):
    platform: str  # telegram | discord
    platform_user_id: str
    username: Optional[str] = None
