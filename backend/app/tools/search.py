"""Web search backed by Tavily (search engine first)."""
import logging
from typing import Any, Dict, List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


async def search_web(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("Masukkan topik yang ingin dicari.")
    if not settings.TAVILY_API_KEY:
        return {
            "success": False,
            "error": "Pencarian web belum aktif: TAVILY_API_KEY belum dikonfigurasi di .env",
            "results": [],
        }

    max_results = max(1, min(int(args.get("max_results", 5)), 8))
    logger.info("Running Tavily search for user %s q=%s", user_id, query[:80])
    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query[:500],
        "search_depth": "basic",
        "topic": "general",
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(TAVILY_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as error:
        logger.warning("Tavily search timed out")
        raise RuntimeError("Pencarian web kehabisan waktu. Coba lagi sebentar.") from error
    except httpx.HTTPStatusError as error:
        logger.warning("Tavily returned HTTP %s", error.response.status_code)
        raise RuntimeError(
            f"Pencarian web gagal (Tavily HTTP {error.response.status_code})."
        ) from error
    except httpx.RequestError as error:
        logger.warning("Tavily request failed: %s", type(error).__name__)
        raise RuntimeError("Layanan pencarian web tidak dapat dihubungi.") from error

    results: List[Dict[str, Any]] = []
    for item in data.get("results") or []:
        results.append({
            "title": item.get("title") or "(tanpa judul)",
            "url": item.get("url") or "",
            "snippet": (item.get("content") or item.get("snippet") or "")[:400],
        })

    return {
        "success": True,
        "query": query,
        "answer": "",
        "results": results,
        "provider": "tavily",
    }


def format_search_results(data: Dict[str, Any], *, use_ai_hint: bool = True) -> str:
    """Format search engine results for user (no AI)."""
    if not data.get("success"):
        return data.get("error") or "Pencarian gagal."

    lines = [f"🔍 **Hasil pencarian:** `{data.get('query', '')}`", ""]
    answer = (data.get("answer") or "").strip()
    if answer:
        lines.append(f"**Ringkasan mesin pencari:**\n{answer}")
        lines.append("")

    results = data.get("results") or []
    if not results:
        lines.append("_Tidak ada hasil._")
    else:
        lines.append("**Sumber:**")
        for i, r in enumerate(results, 1):
            title = r.get("title") or "(tanpa judul)"
            url = r.get("url") or ""
            snippet = (r.get("snippet") or "").strip()
            lines.append(f"{i}. **{title}**")
            if snippet:
                lines.append(f"   {snippet[:200]}{'…' if len(snippet) > 200 else ''}")
            if url:
                lines.append(f"   {url}")
            lines.append("")

    if use_ai_hint:
        lines.append(
            "_Ini hasil search engine (bukan AI). "
            "Kalau mau dirangkum AI, bilang: `pake ai [topik]`_"
        )
    return "\n".join(lines).strip()
