"""Persistence helpers and cross-platform identity resolution."""
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID
import logging

from sqlalchemy import select, and_, update, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import AsyncSessionLocal
from app.database.models.user import User, PlatformAccount, PlatformLinkCode
from app.database.models.event import Event
from app.database.models.task import Task
from app.database.models.reminder import Reminder
from app.database.models.memory import Memory
from app.database.models.note import Note
from app.database.models.document import Document
from app.database.models.study import Course, StudyPlan
from app.database.models.summary import DailySummaryDelivery
from sqlalchemy.exc import IntegrityError
from app.database.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)


def _tz(name: str = "Asia/Jakarta"):
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("UTC")


async def get_or_create_user(
    platform: str,
    platform_user_id: str,
    username: Optional[str] = None,
) -> User:
    async with AsyncSessionLocal() as db:
        account = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == platform,
                PlatformAccount.platform_user_id == str(platform_user_id),
            )
        )
        if account:
            return await db.get(User, account.user_id)

        user = User(name=username or f"{platform}_{platform_user_id}")
        db.add(user)
        await db.flush()
        account = PlatformAccount(
            user_id=user.id,
            platform=platform,
            platform_user_id=str(platform_user_id),
            username=username,
        )
        db.add(account)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Created user {user.id} for {platform}:{platform_user_id}")
        return user


async def get_or_create_conversation(
    user_id: str, platform: str, platform_chat_id: Optional[str] = None
) -> Conversation:
    owner_id = UUID(str(user_id))
    async with AsyncSessionLocal() as db:
        conversation = await db.scalar(
            select(Conversation)
            .where(
                Conversation.user_id == owner_id,
                Conversation.platform == platform,
                Conversation.platform_chat_id == platform_chat_id,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        if conversation:
            return conversation
        conversation = Conversation(
            user_id=owner_id,
            platform=platform,
            platform_chat_id=platform_chat_id,
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation


async def get_conversation_history(conversation_id: str, limit: int = 12) -> List[Dict[str, str]]:
    conversation_uuid = UUID(str(conversation_id))
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(
                Message.conversation_id == conversation_uuid,
                Message.role.in_(["USER", "ASSISTANT"]),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        messages = list(reversed(result.scalars().all()))
    return [
        {"role": "user" if message.role == "USER" else "assistant", "content": message.content}
        for message in messages
    ]


async def save_conversation_message(
    conversation_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    conversation_uuid = UUID(str(conversation_id))
    async with AsyncSessionLocal() as db:
        db.add(
            Message(
                conversation_id=conversation_uuid,
                role=role.upper(),
                content=content,
                metadata_=metadata,
            )
        )
        conversation = await db.get(Conversation, conversation_uuid)
        if conversation:
            conversation.updated_at = datetime.utcnow()
        await db.commit()


async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    platform: str,
    platform_user_id: str,
    message_id: Optional[str] = None,
) -> None:
    await save_conversation_message(
        conversation_id,
        role,
        content,
        {
            "platform": platform,
            "platform_user_id": str(platform_user_id),
            "message_id": message_id,
        },
    )


async def get_upcoming_events(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    now = datetime.now(ZoneInfo("UTC")).replace(tzinfo=None)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Event)
            .where(
                Event.user_id == UUID(str(user_id)),
                Event.status == "ACTIVE",
                Event.start_at >= now,
            )
            .order_by(Event.start_at)
            .limit(limit)
        )
        events = result.scalars().all()
    return [
        {
            "id": str(event.id),
            "title": event.title,
            "start_at": event.start_at.isoformat() if event.start_at else None,
            "category": event.category,
        }
        for event in events
    ]


async def link_platform_account(
    user_id: str,
    platform: str,
    platform_user_id: str,
    username: Optional[str] = None,
) -> str:
    owner_id = UUID(str(user_id))
    if platform not in {"telegram", "discord"}:
        raise ValueError("Platform tidak didukung.")

    async with AsyncSessionLocal() as db:
        account = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.platform == platform,
                PlatformAccount.platform_user_id == str(platform_user_id),
            )
        )
        if account and str(account.user_id) == str(user_id):
            return "already_linked"

        target_user_id = account.user_id if account else None
        target_user = await db.get(User, target_user_id) if target_user_id else None
        source_user = await db.get(User, owner_id)
        if not source_user:
            raise ValueError("Akun PersonalAI sumber tidak ditemukan.")

        if target_user and target_user.id != source_user.id:
            # Preserve existing data if this platform previously auto-created its own user.
            for model in (
                Event,
                Task,
                Reminder,
                Memory,
                Note,
                Document,
                Course,
                StudyPlan,
                Conversation,
                DailySummaryDelivery,
                PlatformLinkCode,
            ):
                await db.execute(
                    update(model)
                    .where(model.user_id == target_user.id)
                    .values(user_id=source_user.id)
                )
            for field in ("university", "major", "semester", "preferences"):
                if getattr(source_user, field) is None:
                    setattr(source_user, field, getattr(target_user, field))
            await db.delete(target_user)
            account.user_id = source_user.id
            account.username = username or account.username
        elif account:
            account.user_id = source_user.id
        else:
            db.add(
                PlatformAccount(
                    user_id=source_user.id,
                    platform=platform,
                    platform_user_id=str(platform_user_id),
                    username=username,
                )
            )

        await db.commit()
        return "linked"


def parse_remind_at(
    day_hint: Optional[str],
    time_str: Optional[str],
    tz_name: str = "Asia/Jakarta",
) -> datetime:
    """Convert a local day/time into naive UTC for MySQL DATETIME storage."""
    now = datetime.now(_tz(tz_name))
    base = now.replace(second=0, microsecond=0)

    day = (day_hint or "hari ini").lower()
    if day == "besok":
        base = base + timedelta(days=1)
    elif day == "lusa":
        base = base + timedelta(days=2)
    # hari ini = base already today

    if time_str:
        # format HH.MM or HH:MM
        parts = time_str.replace(":", ".").split(".")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        base = base.replace(hour=h, minute=m)
    else:
        base = base + timedelta(hours=1)

    return base.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


async def save_reminder(
    user_id: str,
    title: str,
    remind_at: datetime,
    event_id: Optional[str] = None,
) -> Reminder:
    async with AsyncSessionLocal() as db:
        rem = Reminder(
            user_id=user_id,
            title=title,
            remind_at=remind_at,
            event_id=event_id,
            status="PENDING",
        )
        db.add(rem)
        await db.commit()
        await db.refresh(rem)
        return rem


async def save_event(
    user_id: str,
    title: str,
    start_at: datetime,
    category: str = "OTHER",
    end_at: Optional[datetime] = None,
) -> Event:
    async with AsyncSessionLocal() as db:
        ev = Event(
            user_id=user_id,
            title=title,
            start_at=start_at,
            end_at=end_at,
            category=category,
            status="ACTIVE",
        )
        db.add(ev)
        await db.commit()
        await db.refresh(ev)
        return ev


async def save_task(
    user_id: str,
    title: str,
    deadline: Optional[datetime] = None,
    priority: str = "MEDIUM",
) -> Task:
    async with AsyncSessionLocal() as db:
        task = Task(
            user_id=user_id,
            title=title,
            deadline=deadline,
            priority=priority,
            status="TODO",
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        return task


async def save_memory(user_id: str, content: str, category: str = "OTHER") -> Memory:
    async with AsyncSessionLocal() as db:
        mem = Memory(user_id=user_id, content=content, category=category)
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        return mem


async def get_today_items(
    user_id: str,
    tz_name: str = "Asia/Jakarta",
) -> Dict[str, List[Any]]:
    """Fetch today's data using local-day boundaries converted to UTC storage."""
    local_now = datetime.now(_tz(tz_name))
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end = local_end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(
                select(Event).where(
                    and_(
                        Event.user_id == user_id,
                        Event.status == "ACTIVE",
                        Event.start_at >= start,
                        Event.start_at < end,
                    )
                ).order_by(Event.start_at)
            )
        ).scalars().all()

        reminders = (
            await db.execute(
                select(Reminder).where(
                    and_(
                        Reminder.user_id == user_id,
                        Reminder.status == "PENDING",
                        Reminder.remind_at >= start,
                        Reminder.remind_at < end,
                    )
                ).order_by(Reminder.remind_at)
            )
        ).scalars().all()

        tasks = (
            await db.execute(
                select(Task).where(
                    and_(
                        Task.user_id == user_id,
                        Task.status.in_(["TODO", "IN_PROGRESS"]),
                    )
                ).order_by(Task.deadline)
            )
        ).scalars().all()

        memories = (
            await db.execute(
                select(Memory)
                .where(Memory.user_id == user_id)
                .order_by(Memory.created_at.desc())
                .limit(20)
            )
        ).scalars().all()

    return {
        "events": list(events),
        "reminders": list(reminders),
        "tasks": list(tasks),
        "memories": list(memories),
    }


async def get_due_reminders(before: datetime) -> List[Reminder]:
    async with AsyncSessionLocal() as db:
        cutoff = before.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) if before.tzinfo else before
        result = await db.execute(select(Reminder).where(
            and_(Reminder.status == "PENDING", Reminder.remind_at <= cutoff)
        ).order_by(Reminder.remind_at).limit(100))
        return list(result.scalars().all())


async def claim_due_reminders(before: datetime, limit: int = 100) -> List[Dict[str, Any]]:
    cutoff = before.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) if before.tzinfo else before
    stale_claim = cutoff - timedelta(minutes=5)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Reminder)
            .where(
                or_(
                    and_(
                        Reminder.status == "PENDING",
                        Reminder.remind_at <= cutoff,
                        or_(Reminder.next_attempt_at.is_(None), Reminder.next_attempt_at <= cutoff),
                    ),
                    and_(
                        Reminder.status == "SENDING",
                        Reminder.claimed_at <= stale_claim,
                    ),
                )
            )
            .order_by(Reminder.remind_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        reminders = list(result.scalars().all())
        for reminder in reminders:
            reminder.status = "SENDING"
            reminder.claimed_at = cutoff
            reminder.attempt_count += 1
        await db.commit()
        return [
            {
                "id": str(reminder.id),
                "user_id": str(reminder.user_id),
                "title": reminder.title,
                "remind_at": reminder.remind_at,
                "delivery_platform": reminder.delivery_platform,
                "delivery_user_id": reminder.delivery_user_id,
                "attempt_count": reminder.attempt_count,
            }
            for reminder in reminders
        ]


async def finish_reminder_delivery(reminder_id: str, sent: bool, attempt_count: int) -> None:
    async with AsyncSessionLocal() as db:
        reminder = await db.scalar(select(Reminder).where(Reminder.id == UUID(str(reminder_id))))
        if not reminder or reminder.status != "SENDING":
            return
        reminder.claimed_at = None
        if sent:
            reminder.status = "SENT"
            reminder.sent_at = datetime.utcnow()
            reminder.next_attempt_at = None
        else:
            reminder.status = "PENDING"
            delay = min(60 * (2 ** max(0, attempt_count - 1)), 3600)
            reminder.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay)
        await db.commit()


async def get_daily_summary_targets() -> List[Dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User, PlatformAccount)
            .join(PlatformAccount, PlatformAccount.user_id == User.id)
            .where(User.daily_summary_enabled.is_(True))
        )
        rows = result.all()
    return [
        {
            "user_id": str(user.id),
            "timezone": user.timezone,
            "platform": account.platform,
            "platform_user_id": account.platform_user_id,
        }
        for user, account in rows
    ]


async def claim_daily_summary_delivery(
    user_id: str,
    local_date: date,
    platform: str,
    platform_user_id: str,
    now: datetime,
) -> Dict[str, Any] | None:
    cutoff = now.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) if now.tzinfo else now
    stale_claim = cutoff - timedelta(minutes=5)
    owner_id = UUID(str(user_id))
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                delivery = await db.scalar(
                    select(DailySummaryDelivery)
                    .where(
                        DailySummaryDelivery.user_id == owner_id,
                        DailySummaryDelivery.local_date == local_date,
                        DailySummaryDelivery.platform == platform,
                        DailySummaryDelivery.platform_user_id == platform_user_id,
                    )
                    .with_for_update()
                )
                if delivery:
                    if delivery.status == "SENT":
                        return None
                    if delivery.status == "SENDING" and delivery.claimed_at and delivery.claimed_at > stale_claim:
                        return None
                    if delivery.next_attempt_at and delivery.next_attempt_at > cutoff:
                        return None
                    delivery.status = "SENDING"
                    delivery.claimed_at = cutoff
                    delivery.attempt_count += 1
                else:
                    delivery = DailySummaryDelivery(
                        user_id=owner_id,
                        local_date=local_date,
                        platform=platform,
                        platform_user_id=platform_user_id,
                        status="SENDING",
                        claimed_at=cutoff,
                        attempt_count=1,
                    )
                    db.add(delivery)
                    await db.flush()
                return {
                    "id": str(delivery.id),
                    "user_id": str(delivery.user_id),
                    "local_date": delivery.local_date,
                    "platform": delivery.platform,
                    "platform_user_id": delivery.platform_user_id,
                    "attempt_count": delivery.attempt_count,
                }
    except IntegrityError:
        logger.info("Daily summary claim already exists for a concurrent scheduler.")
        return None


async def finish_daily_summary_delivery(
    delivery_id: str, sent: bool, attempt_count: int
) -> None:
    async with AsyncSessionLocal() as db:
        delivery = await db.scalar(
            select(DailySummaryDelivery).where(
                DailySummaryDelivery.id == UUID(str(delivery_id))
            )
        )
        if not delivery or delivery.status != "SENDING":
            return
        delivery.claimed_at = None
        if sent:
            delivery.status = "SENT"
            delivery.sent_at = datetime.utcnow()
            delivery.next_attempt_at = None
        else:
            delivery.status = "PENDING"
            delay = min(60 * (2 ** max(0, attempt_count - 1)), 3600)
            delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay)
        await db.commit()


async def mark_reminder_sent(reminder_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
        rem = result.scalar_one_or_none()
        if rem:
            rem.status = "SENT"
            rem.sent_at = datetime.utcnow()
            await db.commit()