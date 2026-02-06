from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import TriageConfig
from .database import SQLiteRepository
from .models import (
    AppointmentResult,
    ProcessOutcome,
    RoutingAction,
    Urgency,
)
from .notifications import NotificationDispatcherProtocol, NotificationEvent
from .policy import RoutingPolicy
from .reasoner_protocol import TriageReasoner
from .scheduler import Scheduler


@dataclass
class TriageService:
    repository: SQLiteRepository
    reasoner: TriageReasoner
    policy: RoutingPolicy
    scheduler: Scheduler
    config: TriageConfig
    reasoner_label: str = "unknown"
    notifier: NotificationDispatcherProtocol | None = None
    notifier_label: str = "none"

    def process_intake(
        self,
        *,
        phone: str | None,
        age: int,
        sex: str,
        symptoms: str,
        auto_book_high_urgency: bool,
        always_route_when_model_requests_human: bool,
    ) -> ProcessOutcome:
        with self.repository.connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            patient_id = self.repository.create_patient(
                phone=phone,
                age=age,
                sex=sex,
                symptoms=symptoms,
                conn=conn,
            )
            triage = self.reasoner.analyze(age=age, sex=sex, symptoms=symptoms)
            triage_event_id = self.repository.create_triage_event(
                patient_id=patient_id,
                triage_result=triage,
                conn=conn,
            )
            routing = self.policy.decide(
                triage,
                always_route_when_model_requests_human=always_route_when_model_requests_human,
                auto_book_high_urgency=auto_book_high_urgency,
            )
            self.repository.create_routing_decision(
                triage_event_id=triage_event_id,
                decision=routing,
                conn=conn,
            )

        appointment_result: AppointmentResult | None = None
        queue_id: int | None = None

        if routing.action == RoutingAction.AUTO_BOOK:
            appointment_result = self.scheduler.book(
                patient_id=patient_id,
                triage_event_id=triage_event_id,
                urgency=triage.urgency,
                department=triage.suggested_department,
                note="Auto-booked from intake.",
                allow_preemption=True,
            )
            if appointment_result.status == "ESCALATED":
                queue_id = self.repository.enqueue_case(
                    triage_event_id=triage_event_id,
                    reason=f"Auto-book failed: {appointment_result.note}",
                    priority=triage.urgency.value,
                )
        else:
            queue_id = self.repository.enqueue_case(
                triage_event_id=triage_event_id,
                reason=routing.reason,
                priority=triage.urgency.value,
            )

        if routing.action == RoutingAction.ESCALATE and queue_id is not None:
            self._notify_escalation(
                patient_id=patient_id,
                triage_event_id=triage_event_id,
                queue_id=queue_id,
                urgency=triage.urgency,
                department=triage.suggested_department,
                reason=routing.reason,
            )
        elif (
            appointment_result
            and appointment_result.status == "ESCALATED"
            and triage.urgency.value in self.config.notify_on_urgencies
        ):
            self._notify_escalation(
                patient_id=patient_id,
                triage_event_id=triage_event_id,
                queue_id=queue_id,
                urgency=triage.urgency,
                department=triage.suggested_department,
                reason=appointment_result.note or "Scheduling escalation from intake flow.",
            )

        return ProcessOutcome(
            patient_id=patient_id,
            triage_event_id=triage_event_id,
            triage_result=triage,
            routing_decision=routing,
            appointment_result=appointment_result,
            queue_id=queue_id,
        )

    def list_queue(self, status: str = "PENDING") -> list[dict[str, Any]]:
        return self.repository.list_queue(status=status)

    def book_from_queue(
        self,
        *,
        queue_id: int,
        nurse_name: str,
        department_override: str | None = None,
        urgency_override: Urgency | None = None,
        note: str = "",
    ) -> AppointmentResult:
        queue_item = self.repository.get_queue_item(queue_id)
        if not queue_item:
            raise ValueError(f"Queue item {queue_id} not found.")
        if queue_item["status"] != "PENDING":
            raise ValueError(f"Queue item {queue_id} is not pending.")

        triage_event = self.repository.get_triage_event(queue_item["triage_event_id"])
        if not triage_event:
            raise ValueError("Associated triage event not found.")

        urgency = urgency_override or Urgency(triage_event["urgency"])
        department = department_override or triage_event["suggested_department"]
        appointment = self.scheduler.book(
            patient_id=int(queue_item["patient_id"]),
            triage_event_id=int(queue_item["triage_event_id"]),
            urgency=urgency,
            department=department,
            note=f"Nurse booked from queue by {nurse_name}. {note}".strip(),
            allow_preemption=True,
        )
        if appointment.status in {"BOOKED", "BOOKED_FALLBACK", "PREEMPTED"}:
            self.repository.resolve_queue_item(
                queue_id=queue_id,
                status="BOOKED",
                notes=f"Booked by {nurse_name}. {note}".strip(),
                assigned_to=nurse_name,
            )
        else:
            self.repository.resolve_queue_item(
                queue_id=queue_id,
                status="ESCALATED",
                notes=f"Escalated by {nurse_name}. {appointment.note}",
                assigned_to=nurse_name,
            )
            if urgency.value in self.config.notify_on_urgencies:
                self._notify_escalation(
                    patient_id=int(queue_item["patient_id"]),
                    triage_event_id=int(queue_item["triage_event_id"]),
                    queue_id=queue_id,
                    urgency=urgency,
                    department=department,
                    reason=appointment.note or "Scheduling escalation from nurse queue.",
                )
        return appointment

    def get_triage_summary(self, triage_event_id: int) -> dict[str, Any] | None:
        return self.repository.get_triage_event(triage_event_id)

    def get_dashboard_metrics(self) -> dict[str, int | float]:
        return self.repository.dashboard_metrics()

    def recent_appointments(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.recent_appointments(limit=limit)

    def recent_activity(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.recent_activity(limit=limit)

    def list_departments(self) -> list[str]:
        return self.repository.list_departments()

    def get_audit_view(self, *, role: str, limit: int = 100) -> dict[str, list[dict[str, Any]]]:
        normalized_role = role.strip().lower()
        triage_rows = self.repository.recent_triage_decisions(limit=limit)
        audit_rows = self.repository.recent_audit_log(limit=limit)
        if normalized_role == "admin":
            return {"triage": triage_rows, "audit_log": audit_rows}
        if normalized_role == "nurse":
            return {
                "triage": [self._nurse_view_row(row) for row in triage_rows],
                "audit_log": [self._audit_view_row(row, include_payload=True) for row in audit_rows],
            }
        return {
            "triage": [self._operations_view_row(row) for row in triage_rows],
            "audit_log": [self._audit_view_row(row, include_payload=False) for row in audit_rows],
        }

    @staticmethod
    def parse_urgency(raw: str) -> Urgency:
        return Urgency(raw)

    def _notify_escalation(
        self,
        *,
        patient_id: int,
        triage_event_id: int,
        queue_id: int | None,
        urgency: Urgency,
        department: str,
        reason: str,
    ) -> None:
        if not self.notifier:
            return
        if urgency.value not in self.config.notify_on_urgencies:
            return
        event = NotificationEvent(
            event_type="TRIAGE_ESCALATION",
            urgency=urgency.value,
            message=(
                f"{urgency.value} triage escalation for patient {patient_id}; "
                f"department={department}; reason={reason}"
            ),
            patient_id=patient_id,
            triage_event_id=triage_event_id,
            queue_id=queue_id,
            department=department,
            metadata={"source": "triage_service"},
        )
        try:
            deliveries = self.notifier.dispatch(event)
            self.repository.audit(
                entity_type="triage_events",
                entity_id=triage_event_id,
                action="NOTIFICATION_DISPATCHED",
                payload={
                    "event_type": event.event_type,
                    "urgency": urgency.value,
                    "queue_id": queue_id,
                    "deliveries": [
                        {
                            "channel": item.channel,
                            "status": item.status,
                            "detail": item.detail,
                        }
                        for item in deliveries
                    ],
                },
            )
        except Exception as exc:
            self.repository.audit(
                entity_type="triage_events",
                entity_id=triage_event_id,
                action="NOTIFICATION_FAILED",
                payload={
                    "event_type": event.event_type,
                    "urgency": urgency.value,
                    "queue_id": queue_id,
                    "error": str(exc),
                },
            )

    @staticmethod
    def _mask_phone(phone: str | None) -> str:
        if not phone:
            return "-"
        raw = "".join(ch for ch in phone if ch.isdigit())
        if len(raw) < 4:
            return "***"
        return f"***-***-{raw[-4:]}"

    def _nurse_view_row(self, row: dict[str, Any]) -> dict[str, Any]:
        masked = dict(row)
        masked["phone"] = self._mask_phone(masked.get("phone"))
        return masked

    def _operations_view_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "triage_event_id": row.get("triage_event_id"),
            "created_at": row.get("created_at"),
            "urgency": row.get("urgency"),
            "confidence": row.get("confidence"),
            "suggested_department": row.get("suggested_department"),
            "human_routing_flag": row.get("human_routing_flag"),
            "routing_action": row.get("routing_action"),
            "routing_reason": row.get("routing_reason"),
        }

    def _audit_view_row(self, row: dict[str, Any], *, include_payload: bool) -> dict[str, Any]:
        base = {
            "id": row.get("id"),
            "entity_type": row.get("entity_type"),
            "entity_id": row.get("entity_id"),
            "action": row.get("action"),
            "created_at": row.get("created_at"),
        }
        if include_payload:
            base["payload"] = row.get("payload")
        return base
