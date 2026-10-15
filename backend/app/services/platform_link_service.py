"""Persistent, short-lived one-time codes for linking bot and API accounts."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models.user import PlatformLinkCode
from app.services import store_service

CODE_TTL_SECONDS = 10 * 60
MAX_CODE_ATTEMPTS = 5


def _code_hash(code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


async def _issue_code(user_id: str, source_platform: str) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        code = f"{secrets.randbelow(100_000_000):08d}"
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(PlatformLinkCode).where(
                    or_(
                        PlatformLinkCode.expires_at
                        <= datetime.now(timezone.utc).replace(tzinfo=None),
                        (
                            (PlatformLinkCode.user_id == UUID(str(user_id)))
                            & (PlatformLinkCode.source_platform == source_platform)
                        ),
                    )
                )
            )
            db.add(
                PlatformLinkCode(
                    user_id=UUID(str(user_id)),
                    source_platform=source_platform,
                    code_hash=_code_hash(code),
                    expires_at=datetime.now(timezone.utc).replace(tzinfo=None)
                    + timedelta(seconds=CODE_TTL_SECONDS),
                )
            )
            try:
                await db.commit()
                return code
            except IntegrityError as error:
                await db.rollback()
                original = getattr(error, "orig", None)
                error_code = getattr(original, "args", (None,))[0]
                if error_code != 1062:
                    raise
    raise RuntimeError("Tidak dapat membuat kode connect unik. Coba lagi.")


async def create_link_code(
    platform: str,
    platform_user_id: str,
    username: str | None = None,
) -> str:
    if platform not in {"telegram", "discord"}:
        raise ValueError("Platform tidak didukung.")
    user = await store_service.get_or_create_user(platform, platform_user_id, username)
    return await _issue_code(str(user.id), platform)


async def create_user_link_code(user_id: str) -> str:
    return await _issue_code(str(user_id), "web")


async def consume_link_code(
    code: str,
    platform: str,
    platform_user_id: str,
    username: str | None = None,
) -> str:
    if platform not in {"telegram", "discord"} or not code.isdigit() or len(code) != 8:
        return "invalid_or_expired"
    async with AsyncSessionLocal() as db:
        async with db.begin():
            pending = await db.scalar(
                select(PlatformLinkCode)
                .where(PlatformLinkCode.code_hash == _code_hash(code))
                .with_for_update()
            )
            if not pending:
                return "invalid_or_expired"
            expires_at = pending.expires_at
            if expires_at.tzinfo is not None:
                expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
            if expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
                await db.delete(pending)
                return "invalid_or_expired"
            if pending.source_platform == platform:
                return "same_platform"
            await store_service.link_platform_account(
                str(pending.user_id),
                platform,
                platform_user_id,
                username,
            )
            await db.delete(pending)
            return "linked"
