"""
Test koneksi Discord Bot Token dari .env
Jalankan: python test_discord_connection.py
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
APP_ID = os.getenv("DISCORD_APPLICATION_ID", "").strip()


async def test_connection():
    print("=" * 50)
    print("  PersonalAI — Discord Connection Test")
    print("=" * 50)

    if not TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN tidak ditemukan di .env")
        return False

    if len(TOKEN) < 50:
        print("ERROR: Token terlalu pendek / masih placeholder")
        print(f"Panjang token: {len(TOKEN)}")
        return False

    print(f"Token ditemukan (panjang: {len(TOKEN)} karakter)")
    if APP_ID:
        print(f"Application ID: {APP_ID}")
    else:
        print("WARNING: DISCORD_APPLICATION_ID belum diisi")

    try:
        import discord
        from discord.ext import commands
    except ImportError:
        print("ERROR: discord.py belum terinstall")
        print("Jalankan: pip install discord.py")
        return False

    print("\nMencoba connect ke Discord...")

    intents = discord.Intents.default()
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print("\nBERHASIL TERHUBUNG!")
        print(f"Bot name  : {bot.user}")
        print(f"Bot ID    : {bot.user.id}")
        print(f"Servers   : {len(bot.guilds)}")
        for g in bot.guilds:
            print(f"  - {g.name} (id: {g.id})")
        print("\nToken valid dan bot sudah online.")
        await bot.close()

    try:
        await bot.start(TOKEN)
        return True
    except discord.LoginFailure:
        print("\nLOGIN GAGAL — Token invalid / sudah di-reset")
        print("Cek Discord Developer Portal -> Bot -> Reset Token")
        return False
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    ok = asyncio.run(test_connection())
    sys.exit(0 if ok else 1)
