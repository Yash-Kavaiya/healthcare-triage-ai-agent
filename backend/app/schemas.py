from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Role = Literal["operations", "nurse", "admin"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AuthUserResponse(BaseModel):
    username: str
    role: Role
    full_name: str | None = None
    password_change_required: bool = False


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: AuthUserResponse


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class AuthChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class DepartmentScoreOut(BaseModel):
    department: str
    score: float


class TriageResultOut(BaseModel):
    redacted_symptoms: str
    urgency: str
    confidence: float
    red_flags: list[str]
    department_candidates: list[DepartmentScoreOut]
    suggested_department: str
    rationale: str
    recommended_timeframe_minutes: int
    human_routing_flag: bool


class RoutingDecisionOut(BaseModel):
    action: str
    reason: str
    confidence_threshold: float
    department_threshold: float


class AppointmentResultOut(BaseModel):
    status: str
    appointment_id: int | None = None
    slot_id: int | None = None
    slot_start: str | None = None
    note: str = ""
    preempted_appointment_id: int | None = None


class IntakeRequest(BaseModel):
    phone: str | None = None
    age: int = Field(ge=0, le=120)
    sex: str = Field(min_length=1, max_length=20)
    symptoms: str = Field(min_length=3, max_length=4000)
    auto_book_high_urgency: bool = True
    always_route_when_model_requests_human: bool = True


class IntakeResponse(BaseModel):
    patient_id: int
    triage_event_id: int
    triage_result: TriageResultOut
    routing_decision: RoutingDecisionOut
    appointment_result: AppointmentResultOut | None = None
    queue_id: int | None = None


class QueueBookRequest(BaseModel):
    nurse_name: str = Field(default="triage-nurse", min_length=1, max_length=100)
    department_override: str | None = Field(default=None, max_length=100)
    urgency_override: Literal["EMERGENCY", "URGENT", "SOON", "ROUTINE"] | None = None
    note: str = Field(default="", max_length=500)


class QueueItemOut(BaseModel):
    id: int
    status: str
    priority: str
    reason: str
    created_at: str
    triage_event_id: int
    urgency: str
    confidence: float
    suggested_department: str
    rationale: str
    patient_id: int
    phone: str | None = None
    age: int
    sex: str
    symptoms: str


class QueueListResponse(BaseModel):
    items: list[QueueItemOut]


class QueueBookResponse(BaseModel):
    queue_id: int
    appointment_result: AppointmentResultOut


class DashboardMetricsResponse(BaseModel):
    repeat_patients_in_slots: int
    total_slots: int
    available_slots: int
    booked_slots: int
    slot_utilization_percent: float
    pending_queue: int
    pending_high_priority_queue: int
    total_appointments: int
    auto_booked_appointments: int
    preempted_appointments: int
    triage_events_24h: int
    urgent_cases_24h: int
    avg_confidence_24h: float


class DashboardAppointmentsResponse(BaseModel):
    items: list[dict[str, Any]]


class DashboardActivityResponse(BaseModel):
    items: list[dict[str, Any]]


class AuditResponse(BaseModel):
    role: Role
    triage: list[dict[str, Any]]
    audit_log: list[dict[str, Any]]
