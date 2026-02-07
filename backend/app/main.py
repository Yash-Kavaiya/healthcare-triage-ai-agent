from __future__ import annotations

import ipaddress
import os
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware

from triage_agent import (
    RoutingPolicy,
    SQLiteRepository,
    Scheduler,
    TriageConfig,
    TriageService,
    build_notifier,
    build_reasoner,
)
from triage_agent.models import Urgency

from .auth import AuthManager, AuthUser, get_current_user, require_roles
from .schemas import (
    AdminResetPasswordRequest,
    AppointmentResultOut,
    AuditResponse,
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthResetOnboardingRequest,
    AuthRefreshRequest,
    AuthTokenResponse,
    AuthUserResponse,
    DashboardActivityResponse,
    DashboardAppointmentsResponse,
    DashboardMetricsResponse,
    DepartmentScoreOut,
    HealthResponse,
    IntakeRequest,
    IntakeResponse,
    QueueBookRequest,
    QueueBookResponse,
    QueueListResponse,
    RoutingDecisionOut,
    TriageResultOut,
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
)


def _parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return ["http://localhost:4200", "http://127.0.0.1:4200"]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_trusted_proxy_networks(raw: str | None) -> list[ipaddress._BaseNetwork]:
    if not raw:
        return []
    networks: list[ipaddress._BaseNetwork] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _request_from_trusted_proxy(request: Request, trusted_networks: list[ipaddress._BaseNetwork]) -> bool:
    if not trusted_networks:
        return True
    host = request.client.host if request.client else ""
    if not host:
        return False
    try:
        source_ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(source_ip in network for network in trusted_networks)


def _forwarded_ip_candidate(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = ipaddress.ip_address(value)
        return str(parsed)
    except ValueError:
        return None


def _request_source_ip(request: Request) -> str:
    trust_forwarded = _env_bool("TRIAGE_AUTH_TRUST_X_FORWARDED_FOR", False)
    trusted_networks = _parse_trusted_proxy_networks(os.getenv("TRIAGE_AUTH_TRUSTED_PROXY_CIDRS"))
    if trust_forwarded and _request_from_trusted_proxy(request, trusted_networks):
        forwarded = request.headers.get("x-forwarded-for", "")
        for part in forwarded.split(","):
            candidate = _forwarded_ip_candidate(part)
            if candidate:
                return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _build_service() -> TriageService:
    config = TriageConfig.from_env()
    repository = SQLiteRepository(config.db_path)
    repository.init_db()
    repository.seed_slots_if_empty(config)
    reasoner, reasoner_label = build_reasoner(config)
    notifier = build_notifier(config)
    policy = RoutingPolicy(config)
    scheduler = Scheduler(repository=repository, config=config)
    return TriageService(
        repository=repository,
        reasoner=reasoner,
        policy=policy,
        scheduler=scheduler,
        config=config,
        reasoner_label=reasoner_label,
        notifier=notifier,
        notifier_label=notifier.label,
    )


def _triage_out(value) -> TriageResultOut:
    return TriageResultOut(
        redacted_symptoms=value.redacted_symptoms,
        urgency=value.urgency.value,
        confidence=value.confidence,
        red_flags=value.red_flags,
        department_candidates=[
            DepartmentScoreOut(department=item.department, score=item.score)
            for item in value.department_candidates
        ],
        suggested_department=value.suggested_department,
        rationale=value.rationale,
        recommended_timeframe_minutes=value.recommended_timeframe_minutes,
        human_routing_flag=value.human_routing_flag,
    )


def _routing_out(value) -> RoutingDecisionOut:
    return RoutingDecisionOut(
        action=value.action.value,
        reason=value.reason,
        confidence_threshold=value.confidence_threshold,
        department_threshold=value.department_threshold,
    )


def _appointment_out(value) -> AppointmentResultOut:
    return AppointmentResultOut(
        status=value.status,
        appointment_id=value.appointment_id,
        slot_id=value.slot_id,
        slot_start=value.slot_start,
        note=value.note,
        preempted_appointment_id=value.preempted_appointment_id,
    )


def _auth_user_out(value: AuthUser) -> AuthUserResponse:
    return AuthUserResponse(
        username=value.username,
        role=value.role,  # type: ignore[arg-type]
        full_name=value.full_name,
        password_change_required=value.password_change_required,
        onboarding_completed=value.onboarding_completed,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.triage_service = _build_service()
    app.state.auth_manager = AuthManager.from_env()
    try:
        yield
    finally:
        if hasattr(app.state, "triage_service"):
            delattr(app.state, "triage_service")
        if hasattr(app.state, "auth_manager"):
            delattr(app.state, "auth_manager")


def get_service(request: Request) -> TriageService:
    service = getattr(request.app.state, "triage_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="Service is not initialized.")
    return service


def get_auth_manager(request: Request) -> AuthManager:
    manager = getattr(request.app.state, "auth_manager", None)
    if not manager:
        raise HTTPException(status_code=503, detail="Auth manager is not initialized.")
    return manager


ServiceDep = Annotated[TriageService, Depends(get_service)]
AuthManagerDep = Annotated[AuthManager, Depends(get_auth_manager)]
StaffDep = Annotated[AuthUser, Depends(require_roles("operations", "nurse", "admin"))]
NurseDep = Annotated[AuthUser, Depends(require_roles("nurse", "admin"))]
AdminDep = Annotated[AuthUser, Depends(require_roles("admin"))]
CurrentUserDep = Annotated[AuthUser, Depends(get_current_user)]

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="healthcare-triage-api", version="1.0.0")


@router.post("/api/v1/auth/login", response_model=AuthTokenResponse, tags=["auth"])
def login(payload: AuthLoginRequest, request: Request, auth_manager: AuthManagerDep) -> AuthTokenResponse:
    source_ip = _request_source_ip(request)
    is_allowed, retry_after_seconds = auth_manager.check_login_allowed(payload.username, source_ip)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again later.",
            headers={"Retry-After": str(retry_after_seconds)},
        )

    user = auth_manager.authenticate(payload.username, payload.password)
    if not user:
        is_locked, retry_after_seconds = auth_manager.record_failed_login(payload.username, source_ip)
        if is_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts. Please try again later.",
                headers={"Retry-After": str(retry_after_seconds)},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    auth_manager.record_successful_login(payload.username, source_ip)
    token_pair = auth_manager.issue_token_pair(user)
    return AuthTokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
        token_type="bearer",
        expires_in=auth_manager.access_token_exp_minutes * 60,
        refresh_expires_in=auth_manager.refresh_token_exp_minutes * 60,
        user=_auth_user_out(user),
    )


@router.get("/api/v1/auth/me", response_model=AuthUserResponse, tags=["auth"])
def me(current_user: CurrentUserDep) -> AuthUserResponse:
    return _auth_user_out(current_user)


@router.post("/api/v1/auth/refresh", response_model=AuthTokenResponse, tags=["auth"])
def refresh(payload: AuthRefreshRequest, auth_manager: AuthManagerDep) -> AuthTokenResponse:
    token_pair = auth_manager.rotate_refresh_token(payload.refresh_token)
    return AuthTokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
        token_type="bearer",
        expires_in=token_pair["expires_in"],
        refresh_expires_in=token_pair["refresh_expires_in"],
        user=_auth_user_out(token_pair["user"]),
    )


@router.post("/api/v1/auth/change-password", response_model=AuthTokenResponse, tags=["auth"])
def change_password(
    payload: AuthChangePasswordRequest,
    current_user: CurrentUserDep,
    auth_manager: AuthManagerDep,
) -> AuthTokenResponse:
    updated_user = auth_manager.change_password(
        username=current_user.username,
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    token_pair = auth_manager.issue_token_pair(updated_user)
    return AuthTokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
        token_type="bearer",
        expires_in=token_pair["expires_in"],
        refresh_expires_in=token_pair["refresh_expires_in"],
        user=_auth_user_out(updated_user),
    )


@router.post("/api/v1/auth/logout", tags=["auth"])
def logout(payload: AuthRefreshRequest, auth_manager: AuthManagerDep) -> dict[str, str]:
    auth_manager.revoke_refresh_token(payload.refresh_token)
    return {"status": "ok"}


@router.post("/api/v1/auth/onboarding-complete", response_model=AuthUserResponse, tags=["auth"])
def complete_onboarding(
    current_user: CurrentUserDep,
    auth_manager: AuthManagerDep,
) -> AuthUserResponse:
    if current_user.password_change_required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change is required before onboarding completion.",
        )
    updated_user = auth_manager.complete_onboarding(username=current_user.username)
    return _auth_user_out(updated_user)


@router.post("/api/v1/auth/onboarding-reset", response_model=AuthUserResponse, tags=["auth"])
def reset_onboarding(
    payload: AuthResetOnboardingRequest,
    _: AdminDep,
    auth_manager: AuthManagerDep,
) -> AuthUserResponse:
    updated_user = auth_manager.reset_onboarding(username=payload.username)
    return _auth_user_out(updated_user)


@router.get("/api/v1/users", response_model=UserListResponse, tags=["users"])
def list_users(_: AdminDep, auth_manager: AuthManagerDep) -> UserListResponse:
    users = auth_manager.list_users()
    return UserListResponse(users=[_auth_user_out(user) for user in users])


@router.post("/api/v1/users", response_model=AuthUserResponse, tags=["users"], status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    _: AdminDep,
    auth_manager: AuthManagerDep,
) -> AuthUserResponse:
    user = auth_manager.create_user(
        username=payload.username,
        password=payload.password,
        role=payload.role,
        full_name=payload.full_name,
    )
    return _auth_user_out(user)


@router.put("/api/v1/users/{username}", response_model=AuthUserResponse, tags=["users"])
def update_user(
    username: str,
    payload: UserUpdateRequest,
    _: AdminDep,
    auth_manager: AuthManagerDep,
) -> AuthUserResponse:
    user = auth_manager.update_user(
        username=username,
        role=payload.role,
        full_name=payload.full_name,
    )
    return _auth_user_out(user)


@router.post("/api/v1/users/{username}/reset-password", response_model=AuthUserResponse, tags=["users"])
def admin_reset_password(
    username: str,
    payload: AdminResetPasswordRequest,
    _: AdminDep,
    auth_manager: AuthManagerDep,
) -> AuthUserResponse:
    user = auth_manager.admin_reset_password(
        username=payload.username,
        new_password=payload.new_password,
    )
    return _auth_user_out(user)


@router.delete("/api/v1/users/{username}", tags=["users"], status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    _: AdminDep,
    auth_manager: AuthManagerDep,
) -> None:
    auth_manager.delete_user(username=username)


@router.post("/api/v1/triage/intake", response_model=IntakeResponse, tags=["triage"])
def intake(payload: IntakeRequest, service: ServiceDep, _: StaffDep) -> IntakeResponse:
    outcome = service.process_intake(
        phone=payload.phone,
        age=payload.age,
        sex=payload.sex,
        symptoms=payload.symptoms,
        auto_book_high_urgency=payload.auto_book_high_urgency,
        always_route_when_model_requests_human=payload.always_route_when_model_requests_human,
    )
    return IntakeResponse(
        patient_id=outcome.patient_id,
        triage_event_id=outcome.triage_event_id,
        triage_result=_triage_out(outcome.triage_result),
        routing_decision=_routing_out(outcome.routing_decision),
        appointment_result=_appointment_out(outcome.appointment_result)
        if outcome.appointment_result
        else None,
        queue_id=outcome.queue_id,
    )


@router.get("/api/v1/queue", response_model=QueueListResponse, tags=["queue"])
def list_queue(
    service: ServiceDep,
    _: NurseDep,
    status: str = Query(default="PENDING"),
) -> QueueListResponse:
    items = service.list_queue(status=status)
    return QueueListResponse(items=items)


@router.post("/api/v1/queue/{queue_id}/book", response_model=QueueBookResponse, tags=["queue"])
def book_queue_item(
    queue_id: int,
    payload: QueueBookRequest,
    service: ServiceDep,
    _: NurseDep,
) -> QueueBookResponse:
    urgency = Urgency(payload.urgency_override) if payload.urgency_override else None
    appointment = service.book_from_queue(
        queue_id=queue_id,
        nurse_name=payload.nurse_name,
        department_override=payload.department_override,
        urgency_override=urgency,
        note=payload.note,
    )
    return QueueBookResponse(queue_id=queue_id, appointment_result=_appointment_out(appointment))


@router.get("/api/v1/dashboard/metrics", response_model=DashboardMetricsResponse, tags=["dashboard"])
def dashboard_metrics(service: ServiceDep, _: StaffDep) -> DashboardMetricsResponse:
    return DashboardMetricsResponse(**service.get_dashboard_metrics())


@router.get(
    "/api/v1/dashboard/appointments",
    response_model=DashboardAppointmentsResponse,
    tags=["dashboard"],
)
def dashboard_appointments(
    service: ServiceDep,
    current_user: StaffDep,
    limit: int = Query(default=30, ge=1, le=500),
) -> DashboardAppointmentsResponse:
    return DashboardAppointmentsResponse(
        items=service.dashboard_appointments(role=current_user.role, limit=limit)
    )


@router.get(
    "/api/v1/dashboard/activity",
    response_model=DashboardActivityResponse,
    tags=["dashboard"],
)
def dashboard_activity(
    service: ServiceDep,
    _: StaffDep,
    limit: int = Query(default=30, ge=1, le=500),
) -> DashboardActivityResponse:
    return DashboardActivityResponse(items=service.recent_activity(limit=limit))


@router.get("/api/v1/audit", response_model=AuditResponse, tags=["audit"])
def audit_view(
    service: ServiceDep,
    current_user: StaffDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> AuditResponse:
    payload = service.get_audit_view(role=current_user.role, limit=limit)
    return AuditResponse(role=current_user.role, triage=payload["triage"], audit_log=payload["audit_log"])


def create_app() -> FastAPI:
    app = FastAPI(
        title="Healthcare Triage API",
        version="1.0.0",
        description=(
            "FastAPI backend for AI-assisted healthcare triage with queueing, "
            "scheduling, preemption, auditability, and notifications."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_origins(os.getenv("TRIAGE_API_CORS_ORIGINS")),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
