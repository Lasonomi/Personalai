# Setup Guide — PersonalAI / Budak

## Discord

1. Developer Portal → New Application → Bot
2. Enable **Message Content Intent**
3. OAuth2 URL Generator: scopes `bot` + `applications.commands`
4. Permissions minimal: Read/Send Messages, Read History, Use Slash Commands
5. Invite bot ke server
6. `python test_discord_connection.py`
7. `python run_discord.py`

## Telegram

1. @BotFather → /newbot → dapatkan token
2. Isi `TELEGRAM_BOT_TOKEN` di `.env`
3. `python run_telegram.py`

## OpenAI

1. https://platform.openai.com/api-keys
2. Isi `OPENAI_API_KEY` di `.env`
3. Tanpa key pun bot tetap jalan (rule-based intent), tapi jawaban LLM tidak aktif.

## Database (opsional untuk tahap awal)

```bash
# Local PostgreSQL atau Supabase connection string
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/personalai
```

Lalu di Python:

```python
from app.database.connection import init_db
import asyncio
asyncio.run(init_db())
```
