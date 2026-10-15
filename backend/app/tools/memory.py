"""Memory tools backed by persistent, user-scoped records."""
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import delete, select

from app.database.connection import AsyncSessionLocal
from app.database.models.memory import Memory

MEMORY_CATEGORIES = {
    "PROFILE",
    "ACADEMIC",
    "PREFERENCE",
    "PERSONAL",
    "WORK",
    "LEARNING",
    "TASK",
    "GOAL",
    "RELATIONSHIP",
    "OTHER",
}


def _user_id(value: str) -> UUID:
    return UUID(str(value))


def _serialize(memory: Memory) -> Dict[str, Any]:
    return {
        "id": str(memory.id),
        "content": memory.content,
        "category": memory.category,
        "importance": memory.importance,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


async def save_memory(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    content = str(args.get("content", "")).strip()
    if not content:
        raise ValueError("Isi memory wajib diisi.")
    category = str(args.get("category", "OTHER")).upper()
    if category not in MEMORY_CATEGORIES:
        category = "OTHER"
    importance = max(0.0, min(1.0, float(args.get("importance", 0.5))))
    async with AsyncSessionLocal() as db:
        memory = Memory(
            user_id=_user_id(user_id),
            content=content[:10000],
            category=category,
            importance=importance,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)
        return _serialize(memory)


async def get_memory(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    query = select(Memory).where(Memory.user_id == _user_id(user_id))
    if args.get("category"):
        query = query.where(Memory.category == str(args["category"]).upper())
    search = str(args.get("query", "")).strip()
    if search:
        query = query.where(Memory.content.ilike(f"%{search[:150]}%"))
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            query.order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(25)
        )
        memories = [_serialize(memory) for memory in result.scalars().all()]
    return {"memories": memories, "count": len(memories)}


async def update_memory(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    memory_id = UUID(str(args.get("memory_id", "")))
    content = str(args.get("content", "")).strip()
    if not content:
        raise ValueError("Isi memory baru wajib diisi.")
    async with AsyncSessionLocal() as db:
        memory = await db.scalar(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.user_id == _user_id(user_id),
            )
        )
        if not memory:
            return {"success": False, "error": "Memory tidak ditemukan."}
        memory.content = content[:10000]
        if args.get("category"):
            category = str(args["category"]).upper()
            memory.category = category if category in MEMORY_CATEGORIES else "OTHER"
        await db.commit()
        await db.refresh(memory)
        return _serialize(memory)


async def delete_memory(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    owner_id = _user_id(user_id)
    async with AsyncSessionLocal() as db:
        if args.get("all"):
            result = await db.execute(delete(Memory).where(Memory.user_id == owner_id))
        elif args.get("memory_id"):
            result = await db.execute(
                delete(Memory).where(
                    Memory.id == UUID(str(args["memory_id"])),
                    Memory.user_id == owner_id,
                )
            )
        elif args.get("query"):
            query = str(args["query"]).strip()[:150]
            result = await db.execute(
                delete(Memory).where(
                    Memory.user_id == owner_id,
                    Memory.content.ilike(f"%{query}%"),
                )
            )
        else:
            raise ValueError("Pilih memory_id, query, atau all=true untuk menghapus.")
        await db.commit()
        return {"success": True, "deleted_count": result.rowcount or 0}
