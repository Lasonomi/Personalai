"""
Telegram Bot — Budak
"""
import asyncio
import re
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from dotenv import load_dotenv
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from app.config import settings
from app.services import session_service
from app.database.connection import init_db
from app.ai.orchestrator import orchestrator
from app.services.platform_link_service import create_link_code, consume_link_code
from app.scheduler.reminder_scheduler import reminder_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("budak.telegram")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hai, aku **Budak**.\n\n"
        "Aku bisa bantu kamu mengatur jadwal, tugas, reminder, catatan, "
        "research, belajar, dan berbagai aktivitas lainnya.\n\n"
        "Kamu cukup ngobrol seperti biasa, nggak perlu hafalin command.\n\n"
        "Contoh:\n"
        "• Besok jam 8 aku ada kuliah\n"
        "• Jumat harus kumpul laporan\n"
        "• Ingatkan aku bayar listrik tanggal 15\n"
        "• Hari ini aku ada apa?\n"
        "• Ingat aku lebih suka belajar malam",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **Cara pakai Budak**\n\n"
        "Cukup kirim pesan natural:\n"
        "• Buat jadwal → `Besok jam 10 meeting`\n"
        "• Buat tugas → `Deadline laporan hari Jumat`\n"
        "• Reminder → `Ingetin aku jam 7 beli kado`\n"
        "• Cek jadwal → `Besok aku ada apa?`\n"
        "• Memory → `Ingat aku semester 5 TI`\n"
        "• Search web → `Cari informasi tentang ...`\n"
        "• Search + ringkasan AI → `Pake AI untuk search ...`\n\n"
        "Command:\n"
        "/start — mulai\n"
        "/on — aktifkan Budak\n"
        "/off — nonaktifkan Budak\n"
        "/help — bantuan ini\n"
        "/status — status bot",
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    has_ai = bool(settings.OPENAI_API_KEY or settings.GEMINI_API_KEY)
    await update.message.reply_text(
        f"🟢 Bot online\n"
        f"{'🟢' if has_ai else '🔴'} AI provider: {'terkonfigurasi' if has_ai else 'belum dikonfigurasi'}\n"
        f"Model: {settings.DEFAULT_MODEL}"
    )

async def connect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat or not update.message:
        return
    if update.effective_chat.type != "private":
        await update.message.reply_text("Demi keamanan, gunakan /connect di chat pribadi dengan Budak.")
        return

    code = context.args[0] if context.args else None
    username = update.effective_user.username or update.effective_user.first_name
    try:
        if code:
            result = await consume_link_code(
                code,
                "telegram",
                str(update.effective_user.id),
                username,
            )
            response = {
                "linked": "Akun Telegram dan Discord berhasil dihubungkan; data keduanya sekarang tersedia bersama.",
                "already_linked": "Akun ini sudah terhubung.",
                "same_platform": "Buat kode di Discord jika ingin menghubungkan akun Discord.",
                "invalid_or_expired": "Kode tidak valid atau sudah kedaluwarsa. Buat kode baru di platform lain.",
            }.get(result, "Akun tidak dapat dihubungkan.")
            await update.message.reply_text(response)
            return

        link_code = await create_link_code(
            "telegram",
            str(update.effective_user.id),
            username,
        )
        await update.message.reply_text(
            f"Kode connect: {link_code}\nMasukkan dengan /connect {link_code} di Discord dalam 10 menit."
        )
    except Exception:
        logger.exception("Telegram account linking failed")
        await update.message.reply_text(
            "Akun gagal dihubungkan. Tidak ada data yang dihapus; coba lagi nanti."
        )



async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    session_service.turn_on("telegram", str(update.effective_user.id))
    await update.message.reply_text(
        "🟢 *Budak AKTIF*\nGue dengerin kamu.\nMatikan: /off",
        parse_mode="Markdown",
    )


async def off_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    session_service.turn_off("telegram", str(update.effective_user.id))
    await update.message.reply_text(
        "🔴 *Budak OFF*\nPanggil lagi dengan /on",
        parse_mode="Markdown",
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    user = update.effective_user
    user_id = str(user.id) if user else "unknown"
    # natural on/off (hai budak / makasih budak)
    low = text.lower().strip()
    on_patterns = (
        r"^\s*(hai|halo|hi|hello|hey)\s+budak\b",
        r"^\s*budak\s*[,!]?\s*(hai|halo|hi|hello)?\s*$",
        r"^\s*budak\s+(tolong|bantu|bantuin|aktif)\b",
        r"^\s*(panggil|aktifkan|nyalain|hidupkan)\s+budak\b",
    )
    off_patterns = (
        r"\b(yauda|ya sudah|yaudah|udah dulu|sudah dulu)\b.*\bbudak\b",
        r"\bbudak\b.*\b(yauda|yaudah|udah dulu|pergi|minggir|diam)\b",
        r"^\s*(terima kasih|makasih|thanks)\s+budak\b",
        r"^\s*budak\s+(pergi|minggir|off|diam|berhenti)\b",
        r"^\s*yauda\s+sana\b",
        r"^\s*(sampai jumpa|dadah|bye)\s+budak\b",
    )
    if any(re.search(p, low) for p in on_patterns):
        session_service.turn_on("telegram", user_id)
        await update.message.reply_text(
            "Hai! Budak di sini. Ada yang bisa dibantu?\n"
            "Kalau sudah, bilang: makasih budak / yauda sana"
        )
        return
    if any(re.search(p, low) for p in off_patterns):
        session_service.turn_off("telegram", user_id)
        await update.message.reply_text(
            "Oke, Budak undur diri dulu. Panggil lagi: hai budak"
        )
        return
    if not session_service.is_active("telegram", user_id, is_dm=True):
        await update.message.reply_text(
            "Budak lagi istirahat. Panggil dengan: hai budak"
        )
        return
    session_service.touch("telegram", user_id)

    user = update.effective_user
    user_id = str(user.id)

    # Show typing
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply = await orchestrator.process(
            user_id=user_id,
            message=text,
            platform="telegram",
            metadata={"username": user.username or user.first_name},
        )
    except Exception as e:
        logger.exception("Orchestrator error")
        reply = f"Maaf, ada error: {e}"

    await update.message.reply_text(reply)


async def run_telegram_bot():
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN tidak ada di .env")
        return

    await init_db()
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("on", on_command))
    app.add_handler(CommandHandler("off", off_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("connect", connect_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("✅ Budak Telegram starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    reminder_scheduler.start()
    logger.info("✅ Budak Telegram online")

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping Telegram bot...")
        reminder_scheduler.stop()
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_telegram_bot())
