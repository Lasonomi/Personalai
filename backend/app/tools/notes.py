"""Notes Tools"""
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


async def create_note(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    logger.info(f"[create_note] user={user_id} args={args}")
    return {
        "id": "placeholder-uuid",
        "title": args.get("title"),
        "content": args.get("content"),
        "status": "created",
    }


async def search_notes(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    logger.info(f"[search_notes] user={user_id} query={args.get('query')}")
    return {"notes": [], "count": 0}
