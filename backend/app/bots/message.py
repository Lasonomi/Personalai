"""Unified message format for Telegram & Discord adapters."""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from datetime import datetime


@dataclass
class PersonalAIMessage:
    platform: str
    platform_user_id: str
    platform_username: Optional[str]
    text: str
    conversation_id: Optional[str] = None
    message_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    attachments: List[Any] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


def normalize_telegram(update) -> PersonalAIMessage:
    message = update.effective_message
    user = update.effective_user
    return PersonalAIMessage(
        platform="telegram",
        platform_user_id=str(user.id),
        platform_username=user.username or user.first_name,
        text=message.text or message.caption or "",
        message_id=str(message.message_id) if message else None,
        timestamp=message.date.replace(tzinfo=None) if message and message.date else datetime.utcnow(),
        raw={"update_id": getattr(update, "update_id", None)},
    )


def normalize_discord(message) -> PersonalAIMessage:
    return PersonalAIMessage(
        platform="discord",
        platform_user_id=str(message.author.id),
        platform_username=str(message.author),
        text=message.content or "",
        message_id=str(message.id),
        timestamp=message.created_at.replace(tzinfo=None) if message.created_at else datetime.utcnow(),
        raw={"channel_id": str(message.channel.id)},
    )
