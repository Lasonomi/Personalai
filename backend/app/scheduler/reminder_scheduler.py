"""Poll due reminders and deliver them to the originating chat platform."""
import logging
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings
from app.services import store_service

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self):
        self._scheduler = None

    def start(self):
        if self._scheduler and self._scheduler.running:
            return
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.interval import IntervalTrigger

            self._scheduler = AsyncIOScheduler(timezone="UTC")
            self._scheduler.add_job(
                self.check_due_reminders,
                IntervalTrigger(seconds=30),
                id="check_reminders",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            self._scheduler.add_job(
                self.check_daily_summaries,
                IntervalTrigger(seconds=60),
                id="daily_summaries",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            self._scheduler.start()
            logger.info("Reminder scheduler started (every 30s)")
        except Exception:
            logger.exception("Reminder scheduler could not start")
            raise

    async def check_due_reminders(self):
        reminders = await store_service.claim_due_reminders(datetime.now(timezone.utc))
        for reminder in reminders:
            reminder_id = reminder["id"]
            try:
                await self._deliver(reminder)
            except Exception:
                logger.exception("Reminder delivery failed (reminder_id=%s)", reminder_id)
                await store_service.finish_reminder_delivery(
                    reminder_id, False, reminder["attempt_count"]
                )
            else:
                await store_service.finish_reminder_delivery(
                    reminder_id, True, reminder["attempt_count"]
                )

    async def _deliver(self, reminder: dict[str, Any]) -> None:
        platform = reminder.get("delivery_platform")
        recipient = reminder.get("delivery_user_id")
        if not platform or not recipient:
            raise ValueError("Reminder tidak memiliki platform tujuan atau user ID.")
        content = reminder.get("message") or f"⏰ Pengingat: {reminder['title']}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            if platform == "telegram":
                if not settings.TELEGRAM_BOT_TOKEN:
                    raise RuntimeError("TELEGRAM_BOT_TOKEN belum dikonfigurasi.")
                response = await client.post(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": recipient, "text": content},
                )
                response.raise_for_status()
                body = response.json()
                if not body.get("ok"):
                    raise RuntimeError("Telegram menolak pengiriman reminder.")
                return

            if platform == "discord":
                if not settings.DISCORD_BOT_TOKEN:
                    raise RuntimeError("DISCORD_BOT_TOKEN belum dikonfigurasi.")
                headers = {"Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}"}
                channel_response = await client.post(
                    "https://discord.com/api/v10/users/@me/channels",
                    headers=headers,
                    json={"recipient_id": recipient},
                )
                channel_response.raise_for_status()
                channel_id = channel_response.json().get("id")
                if not channel_id:
                    raise RuntimeError("Discord tidak mengembalikan DM channel.")
                message_response = await client.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=headers,
                    json={"content": content},
                )
                message_response.raise_for_status()
                return

        raise ValueError(f"Platform reminder tidak didukung: {platform}")

    async def check_daily_summaries(self):
        now = datetime.now(timezone.utc)
        targets = await store_service.get_daily_summary_targets()
        for target in targets:
            try:
                zone = ZoneInfo(target["timezone"])
            except Exception:
                zone = ZoneInfo("Asia/Jakarta")
            local_now = now.astimezone(zone)
            if local_now.hour < 8:
                continue
            delivery = await store_service.claim_daily_summary_delivery(
                target["user_id"],
                local_now.date(),
                target["platform"],
                target["platform_user_id"],
                now,
            )
            if not delivery:
                continue
            try:
                message = await self._build_daily_summary(
                    target["user_id"], target["timezone"], local_now
                )
                await self._deliver(
                    {
                        "delivery_platform": target["platform"],
                        "delivery_user_id": target["platform_user_id"],
                        "message": message,
                    }
                )
            except Exception:
                logger.exception(
                    "Daily summary delivery failed (user_id=%s, platform=%s)",
                    target["user_id"],
                    target["platform"],
                )
                await store_service.finish_daily_summary_delivery(
                    delivery["id"], False, delivery["attempt_count"]
                )
            else:
                await store_service.finish_daily_summary_delivery(
                    delivery["id"], True, delivery["attempt_count"]
                )

    async def _build_daily_summary(self, user_id: str, timezone_name: str, local_now: datetime) -> str:
        data = await store_service.get_today_items(user_id, timezone_name)
        lines = [f"🌤️ Ringkasan hari ini — {local_now:%A, %d %B %Y}"]
        events = data["events"]
        tasks = data["tasks"]
        reminders = data["reminders"]
        for event in events[:10]:
            event_time = event.start_at.replace(tzinfo=timezone.utc).astimezone(local_now.tzinfo)
            lines.append(f"• {event_time:%H:%M} — {event.title}")
        if events:
            lines.insert(1, "**Jadwal**")
        due_tasks = [
            task for task in tasks
            if task.deadline and task.deadline.replace(tzinfo=timezone.utc).astimezone(local_now.tzinfo).date() == local_now.date()
        ]
        if due_tasks:
            lines.append("**Tugas dengan deadline hari ini**")
            lines.extend(f"• {task.title}" for task in due_tasks[:10])
        pending_tasks = [task for task in tasks if task.status in {"TODO", "IN_PROGRESS"}]
        if pending_tasks:
            lines.append("**Tugas tertunda**")
            lines.extend(f"• {task.title}" for task in pending_tasks[:5])
        if reminders:
            lines.append("**Pengingat hari ini**")
            for reminder in reminders[:10]:
                reminder_time = reminder.remind_at.replace(tzinfo=timezone.utc).astimezone(local_now.tzinfo)
                lines.append(f"• {reminder_time:%H:%M} — {reminder.title}")
        if not events and not due_tasks and not pending_tasks and not reminders:
            lines.append("Belum ada jadwal, tugas, atau pengingat. Harimu masih kosong.")
        return "\n".join(lines)

    def stop(self):
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Reminder scheduler stopped")


reminder_scheduler = ReminderScheduler()
