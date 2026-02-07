from __future__ import annotations

import logging

from .config import TriageConfig
from .gemini_reasoner import GeminiTriageReasoner
from .llm_reasoner import HybridTriageReasoner, OpenAITriageReasoner
from .reasoner import HeuristicTriageReasoner
from .reasoner_protocol import TriageReasoner

logger = logging.getLogger(__name__)


def build_reasoner(config: TriageConfig) -> tuple[TriageReasoner, str]:
    mode = (config.reasoner_mode or "hybrid").strip().lower()
    heuristic = HeuristicTriageReasoner()

    if mode == "heuristic":
        return heuristic, "heuristic"

    def _build_openai() -> OpenAITriageReasoner:
        return OpenAITriageReasoner(
            model=config.openai_model,
            max_output_tokens=config.openai_max_output_tokens,
            request_timeout_seconds=config.openai_timeout_seconds,
            api_key=config.openai_api_key or None,
        )

    def _build_gemini() -> GeminiTriageReasoner:
        return GeminiTriageReasoner(
            model=config.gemini_model,
            max_output_tokens=config.gemini_max_output_tokens,
            request_timeout_seconds=config.gemini_timeout_seconds,
            thinking_level=config.gemini_thinking_level,
            api_key=config.gemini_api_key or None,
        )

    if mode == "openai":
        return _build_openai(), f"openai:{config.openai_model}"

    if mode == "gemini":
        return _build_gemini(), f"gemini:{config.gemini_model}"

    if mode == "hybrid":
        try:
            llm = _build_openai()
            return (
                HybridTriageReasoner(primary=llm, fallback=heuristic),
                f"hybrid(openai:{config.openai_model}->heuristic)",
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize OpenAI reasoner in hybrid mode; using heuristic only. %s",
                exc,
            )
            return heuristic, "heuristic(fallback-init)"

    if mode in {"hybrid-gemini", "hybrid_gemini"}:
        try:
            llm = _build_gemini()
            return (
                HybridTriageReasoner(primary=llm, fallback=heuristic),
                f"hybrid(gemini:{config.gemini_model}->heuristic)",
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize Gemini reasoner in hybrid-gemini mode; using heuristic only. %s",
                exc,
            )
            return heuristic, "heuristic(fallback-init)"

    logger.warning("Unsupported TRIAGE_REASONER_MODE=%s; using heuristic.", mode)
    return heuristic, "heuristic(unsupported-mode)"
