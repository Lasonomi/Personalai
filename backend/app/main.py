"""PersonalAI — FastAPI Application Entry Point"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import settings
from app.database.connection import init_db
from app.api import auth, users, events, tasks, reminders, documents
from app.tools.registry import register_default_tools
from app.scheduler.reminder_scheduler import reminder_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("personalai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PersonalAI...")
    await init_db()
    register_default_tools()
    logger.info("Tools registered.")
    reminder_scheduler.start()
    yield
    reminder_scheduler.stop()
    logger.info("Shutting down PersonalAI...")


app = FastAPI(
    title="PersonalAI",
    description="Personal AI Agent with Budak persona — Telegram + Discord",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(events.router, prefix="/api/events", tags=["Events"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(reminders.router, prefix="/api/reminders", tags=["Reminders"])
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])


@app.get("/")
async def root():
    return {
        "product": "PersonalAI",
        "bot": "Budak",
        "version": "1.0.0",
        "status": "ready",
        "tagline": "Your AI that remembers your life.",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "openai_configured": bool(settings.OPENAI_API_KEY),
        "discord_configured": bool(settings.DISCORD_BOT_TOKEN),
        "telegram_configured": bool(settings.TELEGRAM_BOT_TOKEN),
    }
