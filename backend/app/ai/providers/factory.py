"""AI Provider Factory — provider-agnostic"""
from app.config import settings
from app.ai.providers.base import AIProvider
import logging

logger = logging.getLogger(__name__)


def get_ai_provider() -> AIProvider:
    provider = (settings.AI_PROVIDER or "openai").lower().strip()

    if provider in ("gemini", "google"):
        from app.ai.providers.gemini_provider import GeminiProvider
        p = GeminiProvider()
        logger.info(f"AI Provider: Gemini (configured={p.is_configured})")
        return p

    if provider in ("openai", "gpt"):
        from app.ai.providers.openai_provider import OpenAIProvider
        p = OpenAIProvider()
        logger.info(f"AI Provider: OpenAI (configured={p.is_configured})")
        return p

    if provider == "groq":
        from app.ai.providers.groq_provider import GroqProvider
        p = GroqProvider()
        logger.info(f"AI Provider: Groq (configured={p.is_configured})")
        return p

    # Default: try Gemini if key exists, else OpenAI
    if settings.GEMINI_API_KEY:
        from app.ai.providers.gemini_provider import GeminiProvider
        logger.info("AI Provider: Gemini (auto-detect from GEMINI_API_KEY)")
        return GeminiProvider()

    from app.ai.providers.openai_provider import OpenAIProvider
    logger.info("AI Provider: OpenAI (default)")
    return OpenAIProvider()
