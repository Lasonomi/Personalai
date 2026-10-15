"""Run Discord bot (Budak)"""
import asyncio
from app.bots.discord.bot import run_discord_bot

if __name__ == "__main__":
    print("Starting Budak Discord bot...")
    asyncio.run(run_discord_bot())
