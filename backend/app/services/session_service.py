"""
Session on/off per platform user.
Guild Discord: default OFF until user turns on.
DM: default ON.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Idle auto-off after this long (None = never)
DEFAULT_IDLE_MINUTES = 60


@dataclass
class SessionState:
    active: bool
    activated_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    channel_id: Optional[str] = None  # discord channel scope optional


# key: f"{platform}:{platform_user_id}"
_sessions: Dict[str, SessionState] = {}


def _key(platform: str, platform_user_id: str) -> str:
    return f"{platform}:{platform_user_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_active(
    platform: str,
    platform_user_id: str,
    *,
    is_dm: bool = False,
    idle_minutes: int = DEFAULT_IDLE_MINUTES,
) -> bool:
    k = _key(platform, platform_user_id)
    state = _sessions.get(k)

    if state is None:
        # DM default ON, group/guild default OFF
        return is_dm

    if not state.active:
        return False

    if idle_minutes and state.last_seen:
        if _now() - state.last_seen > timedelta(minutes=idle_minutes):
            state.active = False
            logger.info("Session auto-off (idle) %s", k)
            return False

    return True


def turn_on(platform: str, platform_user_id: str, channel_id: Optional[str] = None) -> SessionState:
    k = _key(platform, platform_user_id)
    now = _now()
    state = SessionState(active=True, activated_at=now, last_seen=now, channel_id=channel_id)
    _sessions[k] = state
    logger.info("Session ON %s", k)
    return state


def turn_off(platform: str, platform_user_id: str) -> SessionState:
    k = _key(platform, platform_user_id)
    state = SessionState(active=False, activated_at=None, last_seen=_now())
    _sessions[k] = state
    logger.info("Session OFF %s", k)
    return state


def touch(platform: str, platform_user_id: str) -> None:
    k = _key(platform, platform_user_id)
    state = _sessions.get(k)
    if state and state.active:
        state.last_seen = _now()


def status_text(platform: str, platform_user_id: str, is_dm: bool = False) -> str:
    active = is_active(platform, platform_user_id, is_dm=is_dm)
    if active:
        return "🟢 **Budak AKTIF** — gue dengerin pesanmu.\nMatikan: `!off` atau `/off`"
    return (
        "🔴 **Budak NONAKTIF** — gue diem dulu.\n"
        "Nyalain: `!on` / `/on` / `budak`"
    )
