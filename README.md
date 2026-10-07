# PersonalAI

**PersonalAI — Your AI that remembers your life.**  
**Budak** is its Telegram and Discord assistant.

Backend: Python, FastAPI, SQLAlchemy async · Local database: MySQL · Bots: Telegram + Discord

> **Database deviation from PRD:** this setup intentionally uses local MySQL, as requested, instead of PostgreSQL/Supabase. Embeddings are stored as JSON; PostgreSQL/pgvector semantic search is not available in this configuration.

## P0 status

| Capability | Status |
|---|---|
| Telegram and Discord identities, including cross-platform linking | Implemented; link codes are stored in MySQL and expire after 10 minutes |
| Profile, timezone, email/password account and bearer-token API auth | Implemented |
| Natural-language event/task/reminder/memory actions | Implemented for common Indonesian wording; Gemini/OpenAI tools handle less deterministic requests |
| Event and task persistence, user-scoped CRUD tools, memory save/retrieve/delete | Implemented |
| Recurring daily/weekly event expansion in schedule queries | Implemented |
| Reminder delivery and daily summary | Implemented; bot/API process must be running and the destination bot token must be configured |
| Daily summary preference | Enabled by default at 08:00 in the user's timezone; change it with `PATCH /api/users/{your-user-id}` |

The feature scope beyond P0 (document upload/search, research integrations, quiz generation, study planning, voice, and a web dashboard) is not implemented. General AI chat and AI-assisted update/delete requests require a configured AI provider key; direct P0 actions still work without that key.
When Gemini returns a quota-exceeded response, factual/current questions fall back to Tavily and include available source links. Tool actions still require the AI provider or their deterministic P0 handlers.

## Setup (Windows)

1. Create a MySQL database, for example:

   ```sql
   CREATE DATABASE personalai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

2. In `backend`, create a virtual environment, activate it, and install dependencies:

   ```powershell
   cd D:\website\personal-ai\backend
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Edit `.env`:
   - Set `DATABASE_URL` to `mysql+aiomysql://USER:PASSWORD@localhost:3306/personalai?charset=utf8mb4`.
   - Set a long random `SECRET_KEY`; never use the example value in production.
   - Add `DISCORD_BOT_TOKEN` and/or `TELEGRAM_BOT_TOKEN`.
   - Add `GEMINI_API_KEY` (or select `AI_PROVIDER=openai` and add `OPENAI_API_KEY`) for free-form chat and AI tool calling.
   - Add `TAVILY_API_KEY` to enable live web search for current facts, weather, and news. Restart the bot after changing `.env`.
   - Set `CORS_ORIGINS` to the exact web-app origins if a frontend is introduced.

4. Initialize the database and run the service you need:

   ```powershell
   python init_db.py
   python run_discord.py
   # In another terminal:
   python run_telegram.py
   # Optional authenticated REST API:
   python run_api.py
   ```

   Bot/API startup also creates missing tables and applies additive MySQL compatibility columns. This is a development bootstrap, not a replacement for reviewed Alembic migrations in production. Existing duplicate platform identities stop startup rather than silently weakening account uniqueness.

5. In Discord Developer Portal, enable **Message Content Intent**, then invite the bot with `bot` and `applications.commands` scopes and message-reading/sending permissions. Check `/ping` and `/status`.

## Using Budak

Send a normal message; no game-style command syntax is needed for common P0 actions:

- `Besok jam 8 aku ada kuliah`
- `Jumat harus kumpul laporan`
- `Ingatkan aku bayar listrik tanggal 15 jam 9`
- `Hari ini aku ada apa?` — menampilkan event dan pengingat aktif hari itu.
- `Ingat aku lebih suka belajar malam`

When a date or time is missing, Budak asks instead of guessing. Daily agenda queries include both events and pending reminders, ordered by time. Destructive AI actions ask for confirmation. In Discord, use `/connect` to create a one-time code or `/connect <code>` to consume one. Telegram supports `/connect` in a private chat. To attach a bot account to an API-registered profile, authenticate first, call `POST /api/auth/connect-code`, then send the returned code using `/connect <code>` to the bot.

## REST API

- `POST /api/auth/register` — JSON registration (`name`, `email`, `password`, optional `timezone`); returns a bearer token.
- `POST /api/auth/login` — OAuth2 form fields `username` (email) and `password`.
- `GET /api/auth/me` — current profile.
- `POST /api/auth/connect-code` — issue a short-lived platform-link code.
- Event, task, reminder, and profile endpoints require `Authorization: Bearer <access_token>`. Resource ownership comes from the token, not a caller-supplied `user_id`.
- `PATCH /api/users/{your-user-id}` updates profile settings such as `timezone` and `daily_summary_enabled`.
- API documentation is at `/docs`; health check is at `/health`.

## Validation

From `backend`:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Use `python init_db.py` to check the configured MySQL connection and schema. Do not share bot tokens, AI keys, the database URL, or bearer tokens in logs or support messages.
