"""Run Telegram bot (Budak)"""
import asyncio
from app.bots.telegram.bot import run_telegram_bot

if __name__ == "__main__":
    print("Starting Budak Telegram bot...")
    asyncio.run(run_telegram_bot())
