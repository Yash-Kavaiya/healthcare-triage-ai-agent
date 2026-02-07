from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value if value else default


def _env_csv(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return list(default or [])
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass
class TriageConfig:
    db_path: str = field(default_factory=lambda: os.getenv("TRIAGE_DB_PATH", "triage.db"))
    reasoner_mode: str = field(default_factory=lambda: os.getenv("TRIAGE_REASONER_MODE", "hybrid"))
    openai_model: str = field(default_factory=lambda: os.getenv("TRIAGE_OPENAI_MODEL", "gpt-4o-mini"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_timeout_seconds: float = 20.0
    openai_max_output_tokens: int = 500
    gemini_model: str = field(
        default_factory=lambda: os.getenv("TRIAGE_GEMINI_MODEL", "gemini-3-flash-preview")
    )
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_timeout_seconds: float = 20.0
    gemini_max_output_tokens: int = 500
    gemini_thinking_level: str = "HIGH"
    notifications_enabled: bool = True
    notify_on_urgencies: list[str] = field(default_factory=lambda: ["EMERGENCY", "URGENT"])
    notification_webhook_url: str = field(default_factory=lambda: os.getenv("TRIAGE_NOTIFICATION_WEBHOOK_URL", ""))
    notification_email_webhook_url: str = field(default_factory=lambda: os.getenv("TRIAGE_EMAIL_WEBHOOK_URL", ""))
    notification_sms_webhook_url: str = field(default_factory=lambda: os.getenv("TRIAGE_SMS_WEBHOOK_URL", ""))
    notification_email_to: list[str] = field(default_factory=list)
    notification_sms_to: list[str] = field(default_factory=list)
    notification_timeout_seconds: float = 6.0
    notification_fail_open: bool = True
    auto_book_confidence_threshold: float = 0.80
    department_score_threshold: float = 0.75
    always_route_when_model_requests_human: bool = True
    auto_book_high_urgency: bool = True
    preemption_enabled: bool = True
    fallback_window_minutes: int = 60 * 24 * 90
    seed_days: int = 30
    urgency_windows_minutes: dict[str, int] = field(
        default_factory=lambda: {
            "EMERGENCY": 60 * 4,
            "URGENT": 60 * 48,
            "SOON": 60 * 24 * 7,
            "ROUTINE": 60 * 24 * 28,
        }
    )
    department_providers: dict[str, list[str]] = field(
        default_factory=lambda: {
            "General Medicine": ["Dr. Patel", "Dr. Reed"],
            "Cardiology": ["Dr. Shah", "Dr. Park"],
            "Pulmonology": ["Dr. Khan", "Dr. Evans"],
            "Neurology": ["Dr. Li", "Dr. Garcia"],
            "Orthopedics": ["Dr. Smith", "Dr. Rao"],
            "Dermatology": ["Dr. Kim"],
            "Gastroenterology": ["Dr. Brown"],
        }
    )

    @classmethod
    def from_env(cls) -> "TriageConfig":
        cfg = cls()
        cfg.reasoner_mode = _env_str("TRIAGE_REASONER_MODE", cfg.reasoner_mode).lower()
        cfg.openai_model = _env_str("TRIAGE_OPENAI_MODEL", cfg.openai_model)
        cfg.openai_api_key = _env_str("OPENAI_API_KEY", cfg.openai_api_key)
        cfg.openai_timeout_seconds = _env_float(
            "TRIAGE_OPENAI_TIMEOUT_SECONDS",
            cfg.openai_timeout_seconds,
        )
        cfg.openai_max_output_tokens = _env_int(
            "TRIAGE_OPENAI_MAX_OUTPUT_TOKENS",
            cfg.openai_max_output_tokens,
        )
        cfg.gemini_model = _env_str("TRIAGE_GEMINI_MODEL", cfg.gemini_model)
        cfg.gemini_api_key = _env_str("GEMINI_API_KEY", cfg.gemini_api_key)
        cfg.gemini_timeout_seconds = _env_float(
            "TRIAGE_GEMINI_TIMEOUT_SECONDS",
            cfg.gemini_timeout_seconds,
        )
        cfg.gemini_max_output_tokens = _env_int(
            "TRIAGE_GEMINI_MAX_OUTPUT_TOKENS",
            cfg.gemini_max_output_tokens,
        )
        cfg.gemini_thinking_level = _env_str(
            "TRIAGE_GEMINI_THINKING_LEVEL",
            cfg.gemini_thinking_level,
        ).upper()
        cfg.notifications_enabled = _env_bool(
            "TRIAGE_NOTIFICATIONS_ENABLED",
            cfg.notifications_enabled,
        )
        cfg.notify_on_urgencies = _env_csv(
            "TRIAGE_NOTIFY_ON_URGENCIES",
            cfg.notify_on_urgencies,
        ) or ["EMERGENCY", "URGENT"]
        cfg.notification_webhook_url = _env_str(
            "TRIAGE_NOTIFICATION_WEBHOOK_URL",
            cfg.notification_webhook_url,
        )
        cfg.notification_email_webhook_url = _env_str(
            "TRIAGE_EMAIL_WEBHOOK_URL",
            cfg.notification_email_webhook_url,
        )
        cfg.notification_sms_webhook_url = _env_str(
            "TRIAGE_SMS_WEBHOOK_URL",
            cfg.notification_sms_webhook_url,
        )
        cfg.notification_email_to = _env_csv(
            "TRIAGE_NOTIFICATION_EMAIL_TO",
            cfg.notification_email_to,
        )
        cfg.notification_sms_to = _env_csv(
            "TRIAGE_NOTIFICATION_SMS_TO",
            cfg.notification_sms_to,
        )
        cfg.notification_timeout_seconds = _env_float(
            "TRIAGE_NOTIFICATION_TIMEOUT_SECONDS",
            cfg.notification_timeout_seconds,
        )
        cfg.notification_fail_open = _env_bool(
            "TRIAGE_NOTIFICATION_FAIL_OPEN",
            cfg.notification_fail_open,
        )
        cfg.auto_book_confidence_threshold = _env_float(
            "TRIAGE_CONFIDENCE_THRESHOLD", cfg.auto_book_confidence_threshold
        )
        cfg.department_score_threshold = _env_float(
            "TRIAGE_DEPARTMENT_THRESHOLD", cfg.department_score_threshold
        )
        cfg.always_route_when_model_requests_human = _env_bool(
            "TRIAGE_ALWAYS_ROUTE_MODEL_HUMAN",
            cfg.always_route_when_model_requests_human,
        )
        cfg.auto_book_high_urgency = _env_bool(
            "TRIAGE_AUTO_BOOK_HIGH_URGENCY",
            cfg.auto_book_high_urgency,
        )
        cfg.preemption_enabled = _env_bool(
            "TRIAGE_PREEMPTION_ENABLED",
            cfg.preemption_enabled,
        )
        cfg.fallback_window_minutes = _env_int(
            "TRIAGE_FALLBACK_WINDOW_MINUTES",
            cfg.fallback_window_minutes,
        )
        cfg.seed_days = _env_int("TRIAGE_SEED_DAYS", cfg.seed_days)
        return cfg
