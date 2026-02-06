from __future__ import annotations

from .config import TriageConfig
from .notifications import (
    HookNotificationDispatcher,
    NoopNotificationDispatcher,
    NotificationDispatcherProtocol,
)


def build_notifier(config: TriageConfig) -> NotificationDispatcherProtocol:
    if not config.notifications_enabled:
        return NoopNotificationDispatcher(label="disabled")
    return HookNotificationDispatcher(config=config, label="hooks")
