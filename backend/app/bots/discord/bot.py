"""
Discord Bot — Budak
Natural chat is primary. Slash commands only for /help /settings /connect
"""
import asyncio
import re
import logging
import os
import sys

# Allow running as script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from dotenv import load_dotenv
load_dotenv()

import discord
from discord.ext import commands
from discord import app_commands

from app.config import settings
from app.database.connection import init_db
from app.ai.orchestrator import orchestrator
from app.bots.message import normalize_discord
from app.services.platform_link_service import create_link_code, consume_link_code
from app.scheduler.reminder_scheduler import reminder_scheduler
from app.services import session_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("budak.discord")


class BudakDiscordBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # WAJIB
        intents.guilds = True
        intents.members = False

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.warning(f"Slash sync failed: {e}")

    async def on_command_error(self, context: commands.Context, exception: Exception):
        logger.exception("Discord command failed", exc_info=exception)
        await context.reply("Maaf, command gagal diproses. Coba lagi sebentar.", mention_author=False)

    async def on_ready(self):
        logger.info(f"✅ Budak Discord online as {self.user} (ID: {self.user.id})")
        logger.info(f"   Servers: {len(self.guilds)}")
        for g in self.guilds:
            logger.info(f"   - {g.name}")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="pesanmu | bilang aja natural",
            )
        )

    async def on_message(self, message: discord.Message):
        # Ignore own messages and other bots
        if message.author.bot:
            return

        text = (message.content or "").strip()
        if not text:
            return

        user_id = str(message.author.id)
        is_dm = isinstance(message.channel, discord.DMChannel)
        lower = text.lower().strip()

        # --- Session ON/OFF (bahasa natural) ---
        on_patterns = (
            r"^\s*(hai|halo|hi|hello|hey)\s+budak\b",
            r"^\s*budak\s*[,!]?\s*(hai|halo|hi|hello)?\s*$",
            r"^\s*budak\s+(tolong|bantu|bantuin|aktif|on|nyala)\b",
            r"^\s*(panggil|aktifkan|nyalain|hidupkan)\s+budak\b",
            r"^\s*@?budak\s*$",
        )
        off_patterns = (
            r"\b(yauda|ya sudah|yaudah|udah dulu|sudah dulu|sudah selesai)\b.*\bbudak\b",
            r"\bbudak\b.*\b(yauda|yaudah|udah dulu|pergi|minggir|diam|off)\b",
            r"^\s*(terima kasih|makasih|thanks)\s+budak\b",
            r"^\s*budak\s+(pergi|minggir|off|diam|berhenti)\b",
            r"^\s*(pergi|minggir)\s+sana\b.*\bbudak\b",
            r"^\s*yauda\s+sana\b",
            r"^\s*(sampai jumpa|dadah|bye)\s+budak\b",
        )

        if any(re.search(p, lower) for p in on_patterns):
            session_service.turn_on("discord", user_id, channel_id=str(message.channel.id))
            await message.reply(
                "Hai! Budak di sini. Ada yang bisa dibantu?\n"
                "Kalau sudah, bilang aja: `makasih budak` / `yauda sana`",
                mention_author=False,
            )
            return

        if any(re.search(p, lower) for p in off_patterns):
            session_service.turn_off("discord", user_id)
            await message.reply(
                "Oke, Budak undur diri dulu. "
                "Panggil lagi kapan aja: `hai budak`",
                mention_author=False,
            )
            return

        # Prefix commands (!help etc)
        if text.startswith("!"):
            await self.process_commands(message)
            return

        # Session gate: di server harus ON; di DM default ON
        if not session_service.is_active("discord", user_id, is_dm=is_dm):
            # Diam saja di guild biar tidak spam; di DM kasih hint sekali
            if is_dm:
                await message.reply(
                    "Budak lagi off. Ketik `!on` atau `budak` untuk mengaktifkan.",
                    mention_author=False,
                )
            return

        session_service.touch("discord", user_id)

        async with message.channel.typing():
            try:
                reply = await orchestrator.process(
                    user_id=user_id,
                    message=text,
                    platform="discord",
                    metadata={
                        "channel_id": str(message.channel.id),
                        "username": message.author.display_name,
                        "message_id": str(message.id),
                    },
                )
            except Exception as e:
                logger.exception("Orchestrator error")
                reply = f"Maaf, ada error: {e}"

        if len(reply) > 1900:
            reply = reply[:1900] + "\n\n_(pesan dipotong)_"

        await message.reply(reply, mention_author=False)


# ---------- Slash commands ----------
def setup_slash_commands(bot: BudakDiscordBot):
    @bot.command(name="on")
    async def on_prefix(context: commands.Context):
        session_service.turn_on(
            "discord",
            str(context.author.id),
            channel_id=str(context.channel.id),
        )
        await context.reply(
            "🟢 **Budak AKTIF.** Panggil natural: `hai budak` · undur: `makasih budak`",
            mention_author=False,
        )

    @bot.command(name="off")
    async def off_prefix(context: commands.Context):
        session_service.turn_off("discord", str(context.author.id))
        await context.reply(
            "🔴 **Budak OFF.** Panggil lagi: `hai budak`",
            mention_author=False,
        )

    @bot.tree.command(name="help", description="Bantuan cara pakai Budak")
    async def help_cmd(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Budak — Personal AI Assistant",
            description=(
                "Gue asisten pribadi kamu.\n\n"
                "**On/Off:**\n"
                "• Nyalain: `!on` / `/on` / ketik `budak`\n"
                "• Matikan: `!off` / `/off` / `budak off`\n\n"
                "**Contoh chat (setelah ON):**\n"
                "• `Besok jam 8 aku ada kuliah`\n"
                "• `Ingetin aku pulang jam 4`\n"
                "• `Cari berita AI hari ini` → search engine\n"
                "• `Pake AI untuk search berita AI` → AI merangkum hasil search\n"
            ),
            color=0x5865F2,
        )
        embed.set_footer(text="PersonalAI — Your AI that remembers your life.")
        await interaction.response.send_message(embed=embed)


    @bot.tree.command(name="on", description="Aktifkan Budak (mulai dengar pesanmu)")
    async def on_cmd(interaction: discord.Interaction):
        session_service.turn_on("discord", str(interaction.user.id), channel_id=str(interaction.channel_id))
        await interaction.response.send_message(
            "🟢 **Budak AKTIF.**\nPanggil natural: `hai budak` · undur: `makasih budak`",
            ephemeral=True,
        )

    @bot.tree.command(name="off", description="Nonaktifkan Budak (berhenti dengar)")
    async def off_cmd(interaction: discord.Interaction):
        session_service.turn_off("discord", str(interaction.user.id))
        await interaction.response.send_message(
            "🔴 **Budak OFF.** Panggil lagi: `hai budak`",
            ephemeral=True,
        )

    @bot.tree.command(name="ping", description="Cek apakah bot online")
    async def ping_cmd(interaction: discord.Interaction):
        latency = round(bot.latency * 1000)
        await interaction.response.send_message(f"Pong! Latency: **{latency} ms**")

    @bot.tree.command(name="status", description="Status bot & AI")
    async def status_cmd(interaction: discord.Interaction):
        has_ai = bool(settings.OPENAI_API_KEY or settings.GEMINI_API_KEY)
        embed = discord.Embed(title="Status Budak", color=0x57F287)
        embed.add_field(name="Bot", value="🟢 Online", inline=True)
        embed.add_field(name="AI Provider", value="🟢 Terkonfigurasi" if has_ai else "🔴 Belum diisi", inline=True)
        embed.add_field(name="Model", value=settings.DEFAULT_MODEL, inline=True)
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="connect", description="Hubungkan akun Budak di Telegram dan Discord")
    @app_commands.describe(code="Kode 8 digit dari /connect di platform lain")
    async def connect_cmd(interaction: discord.Interaction, code: str | None = None):
        if not code:
            try:
                link_code = await create_link_code(
                    "discord",
                    str(interaction.user.id),
                    interaction.user.name,
                )
            except Exception:
                logger.exception("Discord link-code creation failed")
                await interaction.response.send_message(
                    "Gagal membuat kode. Coba lagi sebentar.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Kode connect: **{link_code}**\nMasukkan dengan `/connect {link_code}` di Telegram dalam 10 menit.",
                ephemeral=True,
            )
            return

        try:
            result = await consume_link_code(
                code,
                "discord",
                str(interaction.user.id),
                interaction.user.name,
            )
        except Exception:
            logger.exception("Discord account linking failed")
            await interaction.response.send_message(
                "Akun gagal dihubungkan. Tidak ada data yang dihapus; coba lagi nanti.",
                ephemeral=True,
            )
            return

        response = {
            "linked": "Akun Discord dan Telegram berhasil dihubungkan; data keduanya sekarang tersedia bersama.",
            "already_linked": "Akun ini sudah terhubung.",
            "same_platform": "Buat kode di Telegram jika ingin menghubungkan akun Telegram.",
            "invalid_or_expired": "Kode tidak valid atau sudah kedaluwarsa. Buat kode baru di platform lain.",
        }.get(result, "Akun tidak dapat dihubungkan.")
        await interaction.response.send_message(response, ephemeral=True)


async def run_discord_bot():
    token = settings.DISCORD_BOT_TOKEN
    if not token:
        logger.error("DISCORD_BOT_TOKEN tidak ada di .env")
        return

    await init_db()
    bot = BudakDiscordBot()
    setup_slash_commands(bot)
    reminder_scheduler.start()
    try:
        await bot.start(token)
    finally:
        reminder_scheduler.stop()


if __name__ == "__main__":
    asyncio.run(run_discord_bot())
