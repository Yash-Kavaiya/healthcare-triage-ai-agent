from __future__ import annotations

import logging

from .config import TriageConfig
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

    if mode == "openai":
        return _build_openai(), f"openai:{config.openai_model}"

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

    logger.warning("Unsupported TRIAGE_REASONER_MODE=%s; using heuristic.", mode)
    return heuristic, "heuristic(unsupported-mode)"
