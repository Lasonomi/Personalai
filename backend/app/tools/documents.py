"""Document Tools"""
from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


async def search_documents(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Semantic search over uploaded documents (pgvector)"""
    logger.info(f"[search_documents] user={user_id} query={args.get('query')}")
    return {"chunks": [], "count": 0}
