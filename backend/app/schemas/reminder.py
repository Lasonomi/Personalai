from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    remind_at: datetime
    event_id: UUID | None = None
    task_id: UUID | None = None

    @field_validator("remind_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("remind_at harus menyertakan timezone.")
        return value


class ReminderUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    remind_at: datetime | None = None

    @field_validator("remind_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("remind_at harus menyertakan timezone.")
        return value


class ReminderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    event_id: UUID | None
    task_id: UUID | None
    title: str
    remind_at: datetime
    delivery_platform: str | None
    delivery_user_id: str | None
    status: str
    sent_at: datetime | None
    created_at: datetime
