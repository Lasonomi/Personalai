"""Async SQLAlchemy database connection."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import inspect, text
from app.config import settings
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (for development). Prefer Alembic in production."""
    from app.database import models  # noqa: F401 — register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "mysql":
            existing = await conn.run_sync(
                lambda sync_conn: {
                    table: {column["name"] for column in inspect(sync_conn).get_columns(table)}
                    for table in ("users", "conversations", "reminders")
                    if inspect(sync_conn).has_table(table)
                }
            )
            additions = {
                "users": {
                    "password_hash": "VARCHAR(255) NULL",
                    "daily_summary_enabled": "BOOLEAN NOT NULL DEFAULT 1",
                },
                "conversations": {
                    "platform_chat_id": "VARCHAR(128) NULL",
                },
                "reminders": {
                    "delivery_platform": "VARCHAR(32) NULL",
                    "delivery_user_id": "VARCHAR(128) NULL",
                    "claimed_at": "DATETIME NULL",
                    "next_attempt_at": "DATETIME NULL",
                    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                },
            }
            for table, columns in additions.items():
                current = existing.get(table, set())
                for column, definition in columns.items():
                    if column not in current:
                        await conn.execute(
                            text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")
                        )
            has_identity_constraint = await conn.run_sync(
                lambda sync_conn: any(
                    set(constraint.get("column_names") or ())
                    == {"platform", "platform_user_id"}
                    for constraint in inspect(sync_conn).get_unique_constraints(
                        "platform_accounts"
                    )
                )
            )
            if not has_identity_constraint:
                duplicate = await conn.execute(
                    text(
                        "SELECT 1 FROM platform_accounts "
                        "GROUP BY platform, platform_user_id HAVING COUNT(*) > 1 LIMIT 1"
                    )
                )
                if duplicate.first():
                    raise RuntimeError(
                        "Duplicate platform identities must be resolved before adding "
                        "the platform_accounts unique constraint."
                    )
                await conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uq_platform_account_identity "
                        "ON platform_accounts (platform, platform_user_id)"
                    )
                )
    logger.info("Database tables created / verified")
