"""Routes user messages through deterministic P0 actions and provider tool calls."""
import json
import logging
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any

from app.ai.natural_language import (
    event_category,
    extract_recurrence,
    extract_title,
    parse_datetime,
)
from app.ai.providers.base import AIProvider
from app.database.models.user import User
from app.services import store_service
from app.tools.registry import ToolRegistry, create_registry

logger = logging.getLogger(__name__)

INTENTS = {
    "CREATE_EVENT": [
        r"\b(?:jadwalkan|catat|buat|ada)\b.*\b(?:meeting|rapat|kuliah|kelas|acara|janjian|ujian|dokter|gym|olahraga|belajar|pergi|kumpul|event)\b",
        r"\b(?:meeting|rapat|kuliah|kelas|acara|janjian|ujian|dokter|gym|olahraga|belajar|pergi|kumpul)\b.*\b(?:besok|hari ini|senin|selasa|rabu|kamis|jumat|sabtu|minggu|jam|pukul|tanggal)\b",
        r"\b(?:besok|hari ini|lusa|senin|selasa|rabu|kamis|jumat|sabtu|minggu|jam|pukul|tanggal)\b.*\b(?:meeting|rapat|kuliah|kelas|acara|janjian|ujian|dokter|gym|olahraga|belajar|pergi|kumpul)\b",
    ],
    "CREATE_TASK": [
        r"\b(?:buat|tambahkan|catat|ingatkan aku untuk)\b.*\b(?:task|tugas|todo|to-do)\b",
        r"\b(?:harus|perlu|mesti)\b",
        r"\b(?:jangan lupa|todo|to-do)\b",
        r"\bdeadline\b",
    ],
    "CREATE_REMINDER": [
        r"\b(?:ingatkan|ingetin|remind|buat reminder|set reminder|pengingat)\b",
    ],
    "GET_EVENTS": [
        r"\b(?:jadwal|event|acara|agenda)\b.*\b(?:hari ini|besok|minggu ini|pekan ini)\b",
        r"\b(?:ada apa|jadwal apa|agenda apa)\b",
    ],
    "GET_TASKS": [
        r"\b(?:daftar|list|tampilkan|lihat|apa saja|apa aja)\b.*\b(?:task|tugas|todo|to-do)\b",
        r"\b(?:task|tugas|todo|to-do)\b.*\b(?:saya|aku|hari ini|belum selesai)\b",
    ],
    "COMPLETE_TASK": [
        r"\b(?:selesaikan|selesai|bereskan|tandai selesai|complete)\b.*\b(?:task|tugas|todo|to-do)\b",
    ],
    "SAVE_MEMORY": [
        r"\b(?:ingat|inget|simpan|catat)\b.*\b(?:aku|saya|gue|gua|gw|bahwa|kalau|kalo)\b",
        r"\b(?:ingat|inget|simpan|catat)\b.*\b(?:preferensi|memory|memori)\b",
    ],
    "GET_MEMORY": [
        r"\b(?:apa yang kamu ingat|apa kamu ingat|ingatanku|memori saya|memory saya)\b",
    ],
    "DELETE_MEMORY": [
        r"\b(?:lupakan|hapus)\b.*\b(?:memory|memori|ingatanku|ingatan)\b",
    ],
    "GET_TIME": [
        r"^(?:(?:sekarang|hari ini)\s+)?(?:jam|pukul) berapa(?:\s+sekarang)?[?!. ]*$",
        r"^(?:(?:sekarang|hari ini)\s+)?tanggal berapa(?:\s+sekarang)?[?!. ]*$",
        r"^(?:(?:sekarang|hari ini)\s+)?hari apa(?:\s+sekarang)?[?!. ]*$",
        r"\b(?:waktu sekarang|sekarang (?:jam|pukul) berapa|"
        r"(?:jam|pukul) berapa sekarang|sekarang tanggal berapa|"
        r"tanggal berapa sekarang|hari ini tanggal berapa|"
        r"sekarang hari apa|hari apa sekarang|hari ini hari apa)\b",
    ],
    "GREETING": [
        r"^(?:hai|halo|hi|hello|pagi|siang|sore|malam|assalamualaikum)[!. ]*$",
    ],
    "SEARCH_WEB": [
        r"\b(?:cari|carikan|search|google|lookup)\b",
        r"\b(?:apa itu|siapa itu|berapa|kapan|tanggal berapa|hari apa|dimana|di mana)\b",
        r"\b(?:berita|cuaca|harga|info|informasi)\b",
    ],
}

DESTRUCTIVE_TOOLS = {"delete_event", "delete_task", "delete_reminder", "delete_memory"}
MAX_TOOL_ROUNDS = 4
MAX_PENDING_USER_STATES = 1000


class AIOrchestrator:
    def __init__(self, ai_provider: AIProvider | None = None):
        self.ai = ai_provider
        self.tools: ToolRegistry = create_registry()
        self._pending_clarifications: dict[str, dict[str, Any]] = {}
        self._pending_actions: dict[str, dict[str, Any]] = {}

    async def process(
        self,
        message: str,
        platform: str,
        platform_user_id: str | None = None,
        platform_chat_id: str | None = None,
        *,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        username: str | None = None,
        message_id: str | None = None,
    ) -> str:
        metadata = metadata or {}
        platform_user_id = str(platform_user_id or user_id or "")
        platform_chat_id = str(
            platform_chat_id
            or metadata.get("channel_id")
            or metadata.get("chat_id")
            or platform_user_id
        )
        username = username or metadata.get("username")
        message_id = message_id or metadata.get("message_id")
        if not platform_user_id:
            return "Identitas akun tidak ditemukan. Coba kirim pesan lagi."
        message = message.strip()
        if not message:
            return "Kirim pesan yang ingin kamu catat atau tanyakan."
        if len(message) > 4000:
            return "Pesan terlalu panjang. Batasi maksimal 4.000 karakter ya."

        try:
            user = await store_service.get_or_create_user(
                platform, platform_user_id, username
            )
            conversation = await store_service.get_or_create_conversation(
                user.id, platform, platform_chat_id
            )
            history = await store_service.get_conversation_history(conversation.id, limit=12)
            await store_service.save_message(
                conversation.id,
                "user",
                message,
                platform,
                platform_user_id,
                message_id=message_id,
            )
        except Exception:
            logger.exception("Could not load or store user conversation")
            return "Aku belum bisa mengakses database. Pastikan MySQL hidup dan schema sudah diterapkan."

        user_key = f"{platform}:{platform_user_id}"
        self._discard_expired_states()
        try:
            reply = await self._handle_message(
                message, platform, platform_user_id, user, history, user_key
            )
        except Exception:
            logger.exception("Message processing failed")
            reply = "Maaf, terjadi kendala saat memproses pesan. Data yang gagal disimpan tidak dianggap berhasil."
        try:
            await store_service.save_message(
                conversation.id,
                "assistant",
                reply,
                platform,
                platform_user_id,
            )
        except Exception:
            logger.exception("Could not store assistant response")
        return reply

    async def _handle_message(
        self,
        message: str,
        platform: str,
        platform_user_id: str,
        user: User,
        history: list[dict[str, str]],
        user_key: str,
    ) -> str:
        pending_action = self._pending_actions.get(user_key)
        if pending_action:
            if pending_action["expires_at"] <= datetime.now(timezone.utc):
                self._pending_actions.pop(user_key, None)
                return "Konfirmasi sudah kedaluwarsa. Kirim ulang permintaan jika masih diperlukan."
            confirmation = self._confirmation_value(message)
            if confirmation is True:
                self._pending_actions.pop(user_key, None)
                result = await self.tools.execute(
                    pending_action["name"],
                    pending_action["arguments"],
                    user.id,
                )
                return self._format_tool_result(pending_action["name"], result)
            if confirmation is False:
                self._pending_actions.pop(user_key, None)
                return "Oke, tindakan itu dibatalkan."
            return "Aku masih menunggu konfirmasi. Balas **ya** untuk lanjut atau **tidak** untuk membatalkan."

        clarified = self._pending_clarifications.get(user_key)
        if clarified:
            resolved = await self._resolve_clarification(clarified, message, user, user_key)
            if resolved is not None:
                return resolved

        intent = self.detect_intent(message)
        if intent != "CHAT":
            result = await self._try_rule_based(
                intent, message, user, platform, platform_user_id, user_key
            )
            if result is not None:
                return result

        if self.ai is None or not getattr(self.ai, "is_configured", True):
            return (
                "Aku bisa mencatat event, tugas, pengingat, dan memory, tetapi chat AI umum "
                "belum tersedia karena provider AI belum dikonfigurasi."
            )
        return await self._process_with_ai(
            message, user, platform, platform_user_id, history
        )

    async def _try_rule_based(
        self,
        intent: str,
        message: str,
        user: User,
        platform: str,
        platform_user_id: str,
        user_key: str,
    ) -> str | None:
        if intent == "GREETING":
            return "Hai! Aku siap bantu catat jadwal, tugas, pengingat, atau hal yang ingin kamu ingat."
        if intent == "GET_TIME":
            now = self._now(user)
            return f"Sekarang {now:%A, %d %B %Y pukul %H:%M} ({user.timezone})."
        if intent == "SEARCH_WEB":
            return await self._handle_search(message, user)
        if intent == "CREATE_EVENT":
            return await self._create_event(message, user, platform, platform_user_id, user_key)
        if intent == "CREATE_TASK":
            return await self._create_task(message, user, platform, platform_user_id, user_key)
        if intent == "CREATE_REMINDER":
            return await self._create_reminder(message, user, platform, platform_user_id, user_key)
        if intent == "GET_EVENTS":
            return await self._get_schedule(message, user)
        if intent == "GET_TASKS":
            result = await self.tools.execute("get_tasks", {"status": "TODO"}, user.id)
            return self._format_tool_result("get_tasks", result)
        if intent == "COMPLETE_TASK":
            result = await self.tools.execute("get_tasks", {"status": "TODO"}, user.id)
            tasks = result.get("tasks", [])
            task = self._match_item(message, tasks)
            if task is None:
                return self._format_tool_result("get_tasks", result)
            completed = await self.tools.execute(
                "complete_task", {"task_id": task["id"]}, user.id
            )
            return self._format_tool_result("complete_task", completed)
        if intent == "SAVE_MEMORY":
            content = extract_title(message)
            if content == "Aktivitas":
                return "Hal apa yang ingin kamu minta aku ingat?"
            result = await self.tools.execute(
                "save_memory",
                {"content": content, "category": self._memory_category(message)},
                user.id,
            )
            return self._format_tool_result("save_memory", result)
        if intent == "GET_MEMORY":
            result = await self.tools.execute("get_memory", {}, user.id)
            return self._format_tool_result("get_memory", result)
        if intent == "DELETE_MEMORY":
            delete_all = bool(re.search(r"\b(?:semua|seluruh|all)\b", message, re.IGNORECASE))
            query = None
            if not delete_all:
                query = re.sub(
                    r"^\s*(?:lupakan|hapus)\s+(?:(?:semua|seluruh)\s+)?"
                    r"(?:memory|memori|ingatan|ingatanku)?\s*(?:tentang|soal|yang)?\s*",
                    "",
                    message,
                    flags=re.IGNORECASE,
                ).strip(" .,!?:;")
                query = extract_title(query) if query else None
                if query in {None, "", "Aktivitas"}:
                    return "Memory mana yang ingin dihapus? Sebutkan topiknya, atau katakan `hapus semua memory`."
            self._set_pending(self._pending_actions, user_key, {
                "name": "delete_memory",
                "arguments": {"all": True} if delete_all else {"query": query},
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            })
            subject = "semua memory" if delete_all else f"memory tentang **{query}**"
            return f"Kamu yakin ingin menghapus {subject}? Balas **ya** atau **tidak**."
        return None

    async def _create_event(
        self, message: str, user: User, platform: str, platform_user_id: str, user_key: str
    ) -> str:
        title = extract_title(message)
        if title == "Aktivitas":
            return "Apa nama acaranya? Contoh: `Jadwalkan kuliah besok jam 09.00`."
        event_time = parse_datetime(message, user.timezone, require_date=True)
        if event_time is None:
            self._set_pending(self._pending_clarifications, user_key, {
                "intent": "CREATE_EVENT",
                "original": message,
                "title": title,
                "platform": platform,
                "platform_user_id": platform_user_id,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            })
            return f"Kapan **{title}**? Sebutkan tanggal dan jam, misalnya `besok jam 09.00`."
        self._pending_clarifications.pop(user_key, None)
        result = await self.tools.execute(
            "create_event",
            {
                "title": title,
                "start_at": event_time.isoformat(),
                "category": event_category(message),
                "recurrence": extract_recurrence(message),
            },
            user.id,
        )
        response = self._format_tool_result("create_event", result)
        if result.get("success") and result.get("conflicts"):
            response += "\nCatatan: jadwal ini bertabrakan dengan event lain."
        lead_minutes = self._reminder_lead_minutes(message)
        event = result
        if result.get("success") and event and lead_minutes is not None:
            remind_at = event_time - timedelta(minutes=lead_minutes)
            if remind_at > self._now(user):
                reminder = await self.tools.execute(
                    "create_reminder",
                    {
                        "title": f"Pengingat: {title}",
                        "remind_at": remind_at.isoformat(),
                        "event_id": event["id"],
                        "delivery_platform": platform,
                        "delivery_user_id": platform_user_id,
                    },
                    user.id,
                )
                if not reminder.get("success"):
                    response += "\nEvent tersimpan, tetapi pengingat otomatis gagal dibuat."
        return response

    async def _create_task(
        self, message: str, user: User, platform: str, platform_user_id: str, user_key: str
    ) -> str:
        title = extract_title(message)
        if title == "Aktivitas":
            return "Tugas apa yang ingin dicatat?"
        deadline = None
        if re.search(
            r"\b(besok|esok|lusa|hari ini|tanggal|tgl|senin|selasa|rabu|kamis|jum['’]?at|sabtu|minggu)\b",
            message,
            re.IGNORECASE,
        ):
            deadline = parse_datetime(
                message, user.timezone, require_time=False, default_time=time(23, 59)
            )
            if deadline is None:
                self._set_pending(self._pending_clarifications, user_key, {
                    "intent": "CREATE_TASK",
                    "original": message,
                    "title": title,
                    "platform": platform,
                    "platform_user_id": platform_user_id,
                    "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
                })
                return f"Tanggal deadline **{title}** kurang jelas. Tanggal berapa?"
        result = await self.tools.execute(
            "create_task",
            {
                "title": title,
                "deadline": deadline.isoformat() if deadline else None,
                "priority": self._task_priority(message),
                "category": "GENERAL",
            },
            user.id,
        )
        return self._format_tool_result("create_task", result)

    async def _create_reminder(
        self, message: str, user: User, platform: str, platform_user_id: str, user_key: str
    ) -> str:
        title = extract_title(message)
        if title == "Aktivitas":
            return "Apa yang perlu aku ingatkan, dan kapan?"
        remind_at = parse_datetime(message, user.timezone, require_date=True)
        if remind_at is None:
            self._set_pending(self._pending_clarifications, user_key, {
                "intent": "CREATE_REMINDER",
                "original": message,
                "title": title,
                "platform": platform,
                "platform_user_id": platform_user_id,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
            })
            return f"Kapan aku perlu mengingatkanmu tentang **{title}**? Sebutkan tanggal dan jam."
        result = await self.tools.execute(
            "create_reminder",
            {
                "title": title,
                "remind_at": remind_at.isoformat(),
                "delivery_platform": platform,
                "delivery_user_id": platform_user_id,
            },
            user.id,
        )
        return self._format_tool_result("create_reminder", result)

    async def _resolve_clarification(
        self, pending: dict[str, Any], answer: str, user: User, user_key: str
    ) -> str | None:
        if pending["expires_at"] <= datetime.now(timezone.utc):
            self._pending_clarifications.pop(user_key, None)
            return "Permintaan sebelumnya sudah kedaluwarsa. Coba kirim ulang ya."
        intent = pending["intent"]
        combined = f"{pending['original']} {answer}"
        if intent in {"CREATE_EVENT", "CREATE_REMINDER"}:
            parsed = parse_datetime(combined, user.timezone, require_date=True)
            if parsed is None:
                return "Aku masih perlu tanggal dan jam yang jelas, misalnya `besok jam 09.00`."
            self._pending_clarifications.pop(user_key, None)
            if intent == "CREATE_EVENT":
                return await self._create_event(
                    combined,
                    user,
                    pending["platform"],
                    pending["platform_user_id"],
                    user_key,
                )
            return await self._create_reminder(
                combined,
                user,
                pending["platform"],
                pending["platform_user_id"],
                user_key,
            )
        if intent == "CREATE_TASK":
            deadline = parse_datetime(
                combined, user.timezone, require_time=False, default_time=time(23, 59)
            )
            if deadline is None:
                return "Tanggal deadline belum terbaca. Coba tulis tanggal yang lengkap."
            self._pending_clarifications.pop(user_key, None)
            result = await self.tools.execute(
                "create_task",
                {
                    "title": pending["title"],
                    "deadline": deadline.isoformat(),
                    "priority": self._task_priority(combined),
                    "category": "GENERAL",
                },
                user.id,
            )
            return self._format_tool_result("create_task", result)
        return None

    async def _get_schedule(self, message: str, user: User) -> str:
        now = self._now(user)
        if re.search(r"\b(besok|esok)\b", message, re.IGNORECASE):
            start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif re.search(r"\b(minggu ini|pekan ini)\b", message, re.IGNORECASE):
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + (timedelta(days=7) if re.search(r"\b(minggu|pekan)\b", message, re.IGNORECASE) else timedelta(days=1))
        result = await self.tools.execute(
            "get_events",
            {"date_from": start.isoformat(), "date_to": end.isoformat()},
            user.id,
        )
        if result.get("success") is False:
            return str(result.get("error") or "Jadwal belum bisa diambil. Coba lagi sebentar.")
        reminders_result = await self.tools.execute(
            "get_reminders",
            {
                "status": "PENDING",
                "date_from": start.isoformat(),
                "date_to": end.isoformat(),
            },
            user.id,
        )
        if reminders_result.get("success") is False:
            return str(
                reminders_result.get("error")
                or "Pengingat belum bisa diambil. Coba lagi sebentar."
            )

        items = [
            (event, "event")
            for event in result.get("events", [])
        ] + [
            (reminder, "pengingat")
            for reminder in reminders_result.get("reminders", [])
        ]
        if not items:
            return "Tidak ada jadwal atau pengingat di rentang waktu itu."
        items.sort(
            key=lambda item: self._as_utc(item[0].get("start_at") or item[0].get("remind_at"))
        )
        lines = ["Jadwal dan pengingatmu:"]
        for item, kind in items:
            timestamp = item.get("start_at") or item.get("remind_at")
            lines.append(
                f"• {self._format_local_time(timestamp, user.timezone)}"
                f" — {kind.capitalize()}: {item.get('title', 'Aktivitas')}"
            )
        return "\n".join(lines)

    @staticmethod
    def _as_utc(value: str | None) -> datetime:
        parsed = datetime.fromisoformat(value) if value else datetime.max.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    async def _process_with_ai(
        self,
        message: str,
        user: User,
        platform: str,
        platform_user_id: str,
        history: list[dict[str, str]],
    ) -> str:
        context = await self._build_context(user)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"Kamu PersonalAI, asisten pribadi yang ramah. Balas dalam bahasa pengguna "
                    f"(utamakan Bahasa Indonesia), ringkas, jujur, dan jangan mengaku melakukan "
                    f"aksi sebelum tool berhasil. Waktu lokal sekarang: "
                    f"{self._now(user).strftime('%A, %d %B %Y %H:%M')} ({user.timezone}). "
                    f"Gunakan tools untuk membaca/menulis data. Jangan mengarang jadwal, memory, "
                    f"atau status task. Minta tanggal/jam jika ambigu. Untuk cuaca, berita, "
                    f"informasi terkini, atau fakta spesifik yang perlu diverifikasi, gunakan "
                    f"search_web lalu rangkum hasilnya dan sertakan tautan sumber yang relevan. "
                    f"Jangan menyatakan hasil pencarian sebagai prakiraan resmi jika sumbernya "
                    f"tidak menyatakannya. Untuk cuaca, tanyakan kota/lokasi jika belum jelas; "
                    f"zona waktu saja tidak cukup untuk menebak lokasi. Jika tool gagal atau "
                    f"tidak menemukan sumber, jelaskan keterbatasannya dan jangan mengarang. "
                    f"Data konteks: "
                    f"{json.dumps(context, ensure_ascii=False, default=str)}"
                ),
            }
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": message})
        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = await self.ai.chat(
                    messages=messages,
                    tools=self.tools.definitions(),
                )
                tool_calls = (
                    response.get("tool_calls")
                    if isinstance(response, dict)
                    else getattr(response, "tool_calls", None)
                ) or []
                if not tool_calls:
                    error_category = (
                        response.get("error_category")
                        if isinstance(response, dict)
                        else None
                    )
                    if (
                        error_category == "quota_exceeded"
                        and self._should_search_web_fallback(message)
                    ):
                        search_result = await self.tools.execute(
                            "search_web",
                            {"query": message, "max_results": 5},
                            user.id,
                        )
                        return self._format_web_fallback(search_result)
                    content = (
                        response.get("content")
                        if isinstance(response, dict)
                        else getattr(response, "content", None)
                    )
                    return content.strip() if content else "Maaf, aku belum bisa menyusun jawaban."
                messages.append(self._assistant_tool_message(response))
                for call in tool_calls:
                    name, arguments = self._tool_call_values(call)
                    if name in DESTRUCTIVE_TOOLS:
                        key = f"{platform}:{platform_user_id}"
                        self._set_pending(
                            self._pending_actions,
                            key,
                            {
                                "name": name,
                                "arguments": arguments,
                                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
                            },
                        )
                        return self._confirmation_prompt(name)
                    if name == "create_reminder":
                        arguments.setdefault("delivery_platform", platform)
                        arguments.setdefault("delivery_user_id", platform_user_id)
                    result = await self.tools.execute(name, arguments, user.id)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": self._tool_call_id(call),
                            "name": name,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
            return "Aku berhenti setelah beberapa langkah supaya tidak menjalankan terlalu banyak aksi sekaligus."
        except Exception:
            logger.exception("AI provider/tool execution failed")
            return "Maaf, terjadi kendala saat memproses permintaan. Data yang gagal disimpan tidak dianggap berhasil."

    @staticmethod
    def _should_search_web_fallback(message: str) -> bool:
        if AIOrchestrator.detect_intent(message) != "CHAT":
            return False
        return bool(
            re.search(
                r"\b(?:apa|apakah|siapa|kapan|berapa|kenapa|mengapa|bagaimana|"
                r"dimana|di mana|bisakah|bolehkah|jelaskan|carikan|"
                r"cuaca|hujan|gerimis|suhu|prakiraan|weather|berita|terbaru|"
                r"terkini|sekarang|hari ini|malam ini)\b",
                message,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _format_web_fallback(result: dict[str, Any]) -> str:
        if result.get("success") is False:
            error = result.get("error", "")
            if "belum aktif" in error.lower():
                return (
                    "Kuota Gemini hari ini sudah habis dan pencarian web belum aktif. "
                    "Periksa konfigurasi Tavily lalu coba lagi nanti."
                )
            return (
                "Kuota Gemini hari ini sudah habis, dan pencarian web sedang gagal. "
                "Coba lagi nanti."
            )

        answer = str(result.get("answer") or "").strip()
        sources = result.get("results") or []
        if not answer and not sources:
            return (
                "Kuota Gemini hari ini sudah habis dan Tavily tidak menemukan "
                "sumber yang bisa dipakai. Coba lagi nanti."
            )

        lines = [answer] if answer else [
            "Aku menemukan beberapa sumber, tetapi belum mendapat ringkasan langsung:"
        ]
        links = [
            f"• [{str(source.get('title') or 'Sumber')[:120]}]({source['url']})"
            for source in sources[:3]
            if source.get("url", "").startswith(("https://", "http://"))
        ]
        if links:
            lines.extend(["", "Sumber:", *links])
        lines.extend(
            [
                "",
                "_Catatan: kuota Gemini sedang habis; jawaban ini memakai hasil pencarian web._",
            ]
        )
        return "\n".join(lines)

    async def _build_context(self, user: User) -> dict[str, Any]:
        context: dict[str, Any] = {"profile": {"timezone": user.timezone}}
        try:
            memories = await self.tools.execute("get_memory", {}, user.id)
            context["memories"] = memories.get("memories", [])
            upcoming = await store_service.get_upcoming_events(user.id, limit=5)
            context["upcoming_events"] = upcoming
            tasks = await self.tools.execute("get_tasks", {"status": "TODO"}, user.id)
            context["pending_tasks"] = tasks.get("tasks", [])[:5]
        except Exception:
            logger.exception("Could not build personal context")
        return context

    def _now(self, user: User) -> datetime:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(user.timezone))
        except Exception:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo("Asia/Jakarta"))

    @staticmethod
    def _format_local_time(value: str | None, timezone_name: str) -> str:
        if not value:
            return "waktu belum tersedia"
        from zoneinfo import ZoneInfo
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        try:
            local = parsed.astimezone(ZoneInfo(timezone_name))
        except Exception:
            local = parsed.astimezone(ZoneInfo("Asia/Jakarta"))
        return local.strftime("%a, %d %b %Y %H:%M")

    @staticmethod
    def _confirmation_value(message: str) -> bool | None:
        normalized = message.strip().lower().strip("!. ")
        if normalized in {"ya", "iya", "y", "yes", "lanjut", "konfirmasi", "setuju"}:
            return True
        if normalized in {"tidak", "enggak", "nggak", "gak", "no", "n", "batal", "cancel"}:
            return False
        return None

    def _set_pending(
        self,
        target: dict[str, dict[str, Any]],
        key: str,
        value: dict[str, Any],
    ) -> None:
        if key not in target and len(target) >= MAX_PENDING_USER_STATES:
            target.pop(next(iter(target)))
        target[key] = value

    def _discard_expired_states(self) -> None:
        now = datetime.now(timezone.utc)
        for states in (self._pending_actions, self._pending_clarifications):
            for key, state in list(states.items()):
                if state["expires_at"] <= now:
                    del states[key]

    @staticmethod
    def _assistant_tool_message(response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            calls = response.get("tool_calls") or []
            return {
                "role": "assistant",
                "content": response.get("content") or None,
                "tool_calls": [
                    {
                        "id": str(call.get("id", "")),
                        "type": "function",
                        "function": {
                            "name": call.get("name", ""),
                            "arguments": call.get("args", "{}"),
                        },
                    }
                    for call in calls
                ],
            }
        raw = getattr(response, "raw_response", None)
        choices = getattr(raw, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None and hasattr(message, "model_dump"):
                return message.model_dump(exclude_none=True)
            if message is not None:
                return {
                    "role": "assistant",
                    "content": getattr(message, "content", None),
                    "tool_calls": getattr(message, "tool_calls", None),
                }
        calls = getattr(response, "tool_calls", None) or []
        return {
            "role": "assistant",
            "content": getattr(response, "content", None),
            "tool_calls": [call.model_dump(exclude_none=True) if hasattr(call, "model_dump") else call for call in calls],
        }

    @staticmethod
    def _tool_call_values(call: Any) -> tuple[str, dict[str, Any]]:
        if isinstance(call, dict) and "name" in call:
            name = call.get("name")
            raw_arguments = call.get("args", call.get("arguments", {}))
            if isinstance(raw_arguments, str):
                arguments = json.loads(raw_arguments)
            else:
                arguments = raw_arguments
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ValueError("Invalid tool-call response")
            return name, arguments
        function = getattr(call, "function", None)
        if function:
            name = function.name
            raw_arguments = function.arguments
        elif isinstance(call, dict):
            function = call.get("function", {})
            name = function.get("name")
            raw_arguments = function.get("arguments", {})
        else:
            raise ValueError("Unsupported tool-call response")
        if isinstance(raw_arguments, str):
            arguments = json.loads(raw_arguments)
        else:
            arguments = raw_arguments
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ValueError("Invalid tool-call response")
        return name, arguments

    @staticmethod
    def _tool_call_id(call: Any) -> str:
        if isinstance(call, dict):
            return str(call.get("id", ""))
        return str(getattr(call, "id", ""))

    @staticmethod
    def _format_tool_result(name: str, result: dict[str, Any]) -> str:
        if result.get("success") is False:
            return str(result.get("error") or "Permintaan tidak berhasil. Silakan coba lagi.")
        if name == "create_event":
            return f"Event **{result.get('title', 'Event')}** berhasil dicatat."
        if name == "create_task":
            return f"Tugas **{result.get('title', 'Tugas')}** berhasil ditambahkan."
        if name == "complete_task":
            return "Tugas berhasil ditandai selesai."
        if name == "create_reminder":
            return f"Pengingat **{result.get('title', 'Pengingat')}** berhasil dibuat."
        if name == "save_memory":
            return "Oke, aku akan mengingatnya."
        if name == "get_memory":
            memories = result.get("memories", [])
            if not memories:
                return "Belum ada memory yang tersimpan."
            return "Yang aku ingat:\n" + "\n".join(f"• {item.get('content', '')}" for item in memories)
        if name == "get_tasks":
            tasks = result.get("tasks", [])
            if not tasks:
                return "Tidak ada tugas yang tertunda."
            return "Tugas tertundamu:\n" + "\n".join(f"• {item.get('title', 'Tugas')}" for item in tasks)
        if name == "get_events":
            events = result.get("events", [])
            if not events:
                return "Tidak ada jadwal di rentang waktu itu."
            return "Jadwalmu:\n" + "\n".join(
                f"• {item.get('start_at', '?')} — {item.get('title', 'Event')}"
                for item in events
            )
        if name in {"delete_event", "delete_task", "delete_memory", "delete_reminder"}:
            return "Data berhasil dihapus."
        return json.dumps(result, ensure_ascii=False, default=str)

    @staticmethod
    def _confirmation_prompt(tool_name: str) -> str:
        labels = {
            "delete_event": "menghapus event",
            "delete_task": "menghapus tugas",
            "delete_memory": "menghapus memory",
            "delete_reminder": "menghapus pengingat",
        }
        return f"Kamu yakin ingin {labels.get(tool_name, 'melakukan tindakan ini')}? Balas **ya** atau **tidak**."

    @staticmethod
    def _match_item(message: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
        lowered = message.lower()
        matches = [item for item in items if item.get("title", "").lower() in lowered]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _memory_category(message: str) -> str:
        lowered = message.lower()
        if any(word in lowered for word in ("suka", "prefer", "kesukaan")):
            return "PREFERENCE"
        if any(word in lowered for word in ("kerja", "kantor", "kuliah", "kampus", "jabatan")):
            return "PROFILE"
        if any(word in lowered for word in ("teman", "keluarga", "pacar", "sahabat")):
            return "RELATIONSHIP"
        return "FACT"

    @staticmethod
    def _task_priority(message: str) -> str:
        lowered = message.lower()
        if any(word in lowered for word in ("penting banget", "urgent", "mendesak")):
            return "URGENT"
        if "penting" in lowered or "prioritas tinggi" in lowered:
            return "HIGH"
        if "kalau sempat" in lowered or "prioritas rendah" in lowered:
            return "LOW"
        return "MEDIUM"

    @staticmethod
    def _reminder_lead_minutes(message: str) -> int | None:
        lowered = message.lower()
        match = re.search(r"\b(\d+)\s*(menit|minute|jam|hour)\s+sebelum\b", lowered)
        if not match:
            return None
        amount = int(match.group(1))
        return amount * (60 if match.group(2) in {"jam", "hour"} else 1)

    @staticmethod
    def _wants_ai_search(message: str) -> bool:
        """User explicitly asks to use AI for search/explain."""
        msg = message.lower()
        return bool(re.search(
            r"\b(?:pake|pakai|dengan|pakaiin)\s+ai\b|\bai\s+(?:cari|jelasin|jelaskan|rangkum|summarize)\b",
            msg,
        ))

    @staticmethod
    def _strip_ai_trigger(message: str) -> str:
        return re.sub(
            r"(?i)\b(?:pake|pakai|dengan)\s+ai\b|\bai\s+(?:cari|jelasin|jelaskan|rangkum)\b",
            " ",
            message,
        ).strip()

    @staticmethod
    def _extract_search_query(message: str) -> str:
        q = message.strip()
        q = re.sub(r"(?i)^(?:(?:tolong|coba|dong)\s+)+", "", q)
        q = re.sub(r"(?i)^(?:(?:pake|pakai|dengan)\s+ai\s+)?(?:untuk\s+)?", "", q)
        q = re.sub(r"(?i)^(?:cari(?:kan)?|mencari|search|google|lookup)\s+", "", q)
        q = re.sub(r"(?i)^(?:info(?:rmasi)?)\s+(?:tentang|mengenai|soal)\s+", "", q)
        q = re.sub(r"(?i)^(?:tentang|mengenai|soal)\s+", "", q)
        return q.strip() or message.strip()

    async def _handle_search(self, message: str, user: User) -> str:
        """
        Default: search engine only (Tavily).
        If user says 'pake ai' → search then AI summarize.
        """
        use_ai = self._wants_ai_search(message)
        raw = self._strip_ai_trigger(message) if use_ai else message
        query = self._extract_search_query(raw)

        try:
            result = await self.tools.execute(
                "search_web",
                {"query": query, "max_results": 5},
                user.id,
            )
        except Exception as e:
            logger.exception("search_web failed")
            return f"Pencarian gagal: {e}"

        data = result if isinstance(result, dict) else {"success": False, "error": str(result)}

        from app.tools.search import format_search_results

        if not use_ai:
            return format_search_results(data, use_ai_hint=True)

        # AI path: feed search results to model
        if not data.get("success"):
            return data.get("error") or "Pencarian gagal."

        if self.ai is None or not getattr(self.ai, "is_configured", True):
            return format_search_results(data, use_ai_hint=False) + (
                "\n\n_AI belum dikonfigurasi; menampilkan hasil search engine saja._"
            )

        sources = data.get("results") or []
        source_text = "\n".join(
            f"- {s.get('title')}: {s.get('snippet')} ({s.get('url')})" for s in sources[:5]
        )
        answer = data.get("answer") or ""
        prompt = (
            f"Berdasarkan hasil search engine berikut, jawab pertanyaan user secara ringkas "
            f"dalam Bahasa Indonesia. Sertakan fakta dari sumber, jangan mengarang.\n\n"
            f"Pertanyaan: {query}\n\n"
            f"Ringkasan mesin pencari: {answer}\n\n"
            f"Sumber:\n{source_text}"
        )
        try:
            ai_resp = await self.ai.chat(
                messages=[
                    {"role": "system", "content": "Kamu asisten yang merangkum hasil pencarian web dengan jujur."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )
            content = (ai_resp.get("content") or "").strip()
            links = "\n".join(f"• {s.get('url')}" for s in sources[:5] if s.get("url"))
            out = f"🤖 **Jawaban AI (berdasarkan search):**\n{content}"
            if links:
                out += f"\n\n**Sumber:**\n{links}"
            return out
        except Exception as e:
            logger.exception("AI summarize search failed")
            return format_search_results(data, use_ai_hint=False) + f"\n\n_AI gagal merangkum: {e}_"


    @staticmethod
    def detect_intent(message: str) -> str:
        normalized = message.lower().strip()
        if re.search(r"\b(?:deadline|harus|perlu|mesti)\b", normalized):
            return "CREATE_TASK"
        for intent, patterns in INTENTS.items():
            if any(re.search(pattern, normalized) for pattern in patterns):
                return intent
        return "CHAT"


def _configured_provider() -> AIProvider | None:
    from app.config import settings

    provider = settings.AI_PROVIDER.lower()
    if provider == "gemini":
        from app.ai.providers.gemini_provider import GeminiProvider
        return GeminiProvider()
    if provider == "openai":
        from app.ai.providers.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if provider == "groq":
        from app.ai.providers.groq_provider import GroqProvider
        return GroqProvider()
    logger.warning("Unsupported AI_PROVIDER value: %s", provider)
    return None


orchestrator = AIOrchestrator(_configured_provider())
