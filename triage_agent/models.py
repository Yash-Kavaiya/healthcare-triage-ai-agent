from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Urgency(str, Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    SOON = "SOON"
    ROUTINE = "ROUTINE"


class RoutingAction(str, Enum):
    AUTO_BOOK = "AUTO_BOOK"
    QUEUE_REVIEW = "QUEUE_REVIEW"
    ESCALATE = "ESCALATE"


URGENCY_RANK = {
    Urgency.ROUTINE: 1,
    Urgency.SOON: 2,
    Urgency.URGENT: 3,
    Urgency.EMERGENCY: 4,
}


def urgency_rank(value: Urgency | str) -> int:
    urgency = value if isinstance(value, Urgency) else Urgency(value)
    return URGENCY_RANK[urgency]


@dataclass(frozen=True)
class DepartmentScore:
    department: str
    score: float


@dataclass
class TriageResult:
    redacted_symptoms: str
    urgency: Urgency
    confidence: float
    red_flags: list[str]
    department_candidates: list[DepartmentScore]
    suggested_department: str
    rationale: str
    recommended_timeframe_minutes: int
    human_routing_flag: bool

    @property
    def top_department_score(self) -> float:
        if not self.department_candidates:
            return 0.0
        return self.department_candidates[0].score


@dataclass
class RoutingDecision:
    action: RoutingAction
    reason: str
    confidence_threshold: float
    department_threshold: float


@dataclass
class AppointmentResult:
    status: str
    appointment_id: Optional[int] = None
    slot_id: Optional[int] = None
    slot_start: Optional[str] = None
    note: str = ""
    preempted_appointment_id: Optional[int] = None


@dataclass
class ProcessOutcome:
    patient_id: int
    triage_event_id: int
    triage_result: TriageResult
    routing_decision: RoutingDecision
    appointment_result: Optional[AppointmentResult] = None
    queue_id: Optional[int] = None
    metadata: dict[str, str] = field(default_factory=dict)
