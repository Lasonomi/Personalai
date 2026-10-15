# PRD FINAL — PersonalAI
**Version:** 1.0 Final  
**Status:** Product Definition / Ready for Development  
**Platform:** Telegram + Discord  
**AI Interface:** Natural Language Conversation  
**Backend:** Python + FastAPI  
**Database:** PostgreSQL / Supabase  
**Primary Bot Name:** Budak  

## Product Overview
PersonalAI adalah platform Personal AI Agent yang membantu pengguna mengingat, mengatur, merencanakan, mencari informasi, belajar, dan menjalankan berbagai aktivitas personal melalui percakapan natural.

Pengguna tidak perlu mempelajari command khusus. Cukup berbicara seperti berbicara dengan asisten pribadi.

## Bot Persona
**Budak** — persona interface bot untuk Telegram & Discord. Produk tetap bernama PersonalAI.

## Vision
**PersonalAI — Your AI that remembers your life.**

## Core Goals
1. Memory Assistant  
2. Calendar Assistant  
3. Task Assistant  
4. Reminder Assistant  
5. Research Assistant  
6. Learning Assistant  
7. Planning Assistant  
8. Personal AI Agent  

## Core Principle
> "Talk naturally. PersonalAI handles the complexity."

## Architecture Overview
```
User → Message → Intent Detection → Context Retrieval → AI Planning 
→ Tool Execution → Database / External Service → Response → Memory Update
```

Multi-platform: Telegram Adapter + Discord Adapter → Message Layer → AI Orchestrator → Tools → PostgreSQL

## Intent System (Minimal)
CHAT, CREATE/GET/UPDATE/DELETE_EVENT, CREATE/GET/UPDATE/COMPLETE/DELETE_TASK,  
CREATE/GET/UPDATE/DELETE_REMINDER, SAVE/GET/DELETE_MEMORY,  
SEARCH_WEB, RESEARCH, ANALYZE_DOCUMENT, CREATE/GET/UPDATE/DELETE_NOTE,  
CREATE_STUDY_PLAN, GENERATE_QUIZ, GET_DAILY/WEEKLY_SUMMARY,  
CHECK_SCHEDULE, CHECK_CONFLICT, RECOMMEND_TIME

## Key Data Models
- **users** (profile + timezone)
- **platform_accounts** (Telegram/Discord linking)
- **memories** (dengan embedding + category)
- **events** (start_at, end_at, recurrence, category)
- **tasks** (priority, deadline, status)
- **reminders**
- **notes**, **documents**, **document_chunks** (pgvector)
- **conversations**, **messages**
- **courses**, **study_plans**

## Memory Categories
PROFILE, ACADEMIC, PREFERENCE, PERSONAL, WORK, LEARNING, TASK, GOAL, RELATIONSHIP, OTHER

## Event Categories
ACADEMIC, PERSONAL, WORK, SOCIAL, EVENT, HEALTH, STUDY, MEETING, TRAVEL, OTHER

## Task Status / Priority
Status: TODO | IN_PROGRESS | COMPLETED | OVERDUE | CANCELLED  
Priority: LOW | MEDIUM | HIGH | URGENT

## MVP Scope (P0)
- Account (registration, profile, Telegram + Discord linking)
- Natural Language AI + Intent + Tool calling + Context
- Memory (save / retrieve / delete)
- Calendar (CRUD event, categories, recurring, reminder)
- Tasks (create, deadline, priority, status, complete)
- Notification (reminder + daily summary)

## Tech Stack
| Layer | Tech |
|-------|------|
| Backend | Python, FastAPI, Pydantic, SQLAlchemy |
| DB | PostgreSQL (Supabase) + pgvector |
| AI | Provider-agnostic (OpenAI / Gemini / Claude / OpenRouter) |
| Telegram | python-telegram-bot |
| Discord | discord.py |
| Scheduler | APScheduler (MVP) → Celery + Redis |
| Search | Tavily / Brave / SerpAPI |
| Storage | Supabase Storage / S3 |

## Folder Structure
Lihat struktur di root proyek ini (sesuai section 62 PRD).

## Development Roadmap
1. Foundation  
2. Personal Core (Profile, Memory, Intent, Tools)  
3. Productivity (Events, Tasks, Reminders, Daily Briefing)  
4. Intelligence (Search, Research, Smart Scheduling)  
5. Learning (PDF, Quiz, Study Planner)  
6. Advanced Agent (Multi-step, Integrations, Voice, Dashboard)

## Tagline
- Primary: **PersonalAI — Your AI that remembers your life.**
- Indonesian: **PersonalAI — AI pribadi yang mengingat, mengatur, dan membantu hidupmu.**
- Bot: **Budak — Your personal AI assistant.**

## One Sentence Pitch
PersonalAI adalah personal AI agent yang memungkinkan pengguna mengatur jadwal, tugas, reminder, informasi, pembelajaran, dan berbagai aktivitas hidup hanya melalui percakapan natural dengan satu AI bernama Budak, baik melalui Telegram maupun Discord.

---
*Full detailed PRD (sections 1–109) tersedia di source dokumen yang diberikan user.*
