from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from .config import TriageConfig

logger = logging.getLogger(__name__)


@dataclass
class NotificationEvent:
    event_type: str
    urgency: str
    message: str
    patient_id: int
    triage_event_id: int
    department: str
    queue_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationDelivery:
    channel: str
    status: str
    detail: str


class NotificationDispatcherProtocol(Protocol):
    label: str

    def dispatch(self, event: NotificationEvent) -> list[NotificationDelivery]:
        ...


@dataclass
class NoopNotificationDispatcher:
    label: str = "disabled"

    def dispatch(self, event: NotificationEvent) -> list[NotificationDelivery]:
        logger.info(
            "Notification noop for event=%s urgency=%s triage_event_id=%s",
            event.event_type,
            event.urgency,
            event.triage_event_id,
        )
        return [NotificationDelivery(channel="noop", status="SKIPPED", detail="Disabled.")]


@dataclass
class HookNotificationDispatcher:
    config: TriageConfig
    label: str = "hooks"

    def dispatch(self, event: NotificationEvent) -> list[NotificationDelivery]:
        payload = {
            "event_type": event.event_type,
            "urgency": event.urgency,
            "message": event.message,
            "patient_id": event.patient_id,
            "triage_event_id": event.triage_event_id,
            "queue_id": event.queue_id,
            "department": event.department,
            "metadata": event.metadata,
        }

        results: list[NotificationDelivery] = []
        if self.config.notification_webhook_url:
            results.append(
                self._send_http_hook(
                    channel="webhook",
                    url=self.config.notification_webhook_url,
                    payload=payload,
                )
            )

        if self.config.notification_email_webhook_url and self.config.notification_email_to:
            email_payload = {
                "to": self.config.notification_email_to,
                "subject": f"[Triage Alert] {event.urgency} triage escalation",
                "body": event.message,
                "event": payload,
            }
            results.append(
                self._send_http_hook(
                    channel="email",
                    url=self.config.notification_email_webhook_url,
                    payload=email_payload,
                )
            )
        elif self.config.notification_email_to:
            results.append(
                NotificationDelivery(
                    channel="email",
                    status="SKIPPED",
                    detail="Email recipients configured, but no email webhook URL.",
                )
            )

        if self.config.notification_sms_webhook_url and self.config.notification_sms_to:
            sms_payload = {
                "to": self.config.notification_sms_to,
                "message": event.message[:320],
                "event": payload,
            }
            results.append(
                self._send_http_hook(
                    channel="sms",
                    url=self.config.notification_sms_webhook_url,
                    payload=sms_payload,
                )
            )
        elif self.config.notification_sms_to:
            results.append(
                NotificationDelivery(
                    channel="sms",
                    status="SKIPPED",
                    detail="SMS recipients configured, but no SMS webhook URL.",
                )
            )

        if not results:
            results.append(
                NotificationDelivery(
                    channel="hooks",
                    status="SKIPPED",
                    detail="No notification hooks configured.",
                )
            )
        return results

    def _send_http_hook(
        self, *, channel: str, url: str, payload: dict[str, Any]
    ) -> NotificationDelivery:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(
                request,
                timeout=self.config.notification_timeout_seconds,
            ) as response:
                status_code = getattr(response, "status", None) or response.getcode()
            if 200 <= int(status_code) < 300:
                return NotificationDelivery(
                    channel=channel,
                    status="SENT",
                    detail=f"HTTP {status_code}",
                )
            detail = f"HTTP {status_code}"
            if self.config.notification_fail_open:
                return NotificationDelivery(channel=channel, status="FAILED", detail=detail)
            raise RuntimeError(f"{channel} hook failed with {detail}")
        except (URLError, TimeoutError, RuntimeError, OSError) as exc:
            if self.config.notification_fail_open:
                return NotificationDelivery(channel=channel, status="FAILED", detail=str(exc))
            raise
