from triage_agent.config import TriageConfig
from triage_agent.database import SQLiteRepository
from triage_agent.models import RoutingAction
from triage_agent.notifications import NotificationDelivery
from triage_agent.policy import RoutingPolicy
from triage_agent.reasoner import HeuristicTriageReasoner
from triage_agent.scheduler import Scheduler
from triage_agent.service import TriageService


class _SpyNotifier:
    label = "spy"

    def __init__(self) -> None:
        self.events = []

    def dispatch(self, event):
        self.events.append(event)
        return [NotificationDelivery(channel="spy", status="SENT", detail="ok")]


def _build_service(tmp_path, notifier) -> TriageService:
    db_path = str(tmp_path / "service_alerts.db")
    config = TriageConfig(db_path=db_path)
    repo = SQLiteRepository(config.db_path)
    repo.init_db()
    return TriageService(
        repository=repo,
        reasoner=HeuristicTriageReasoner(),
        policy=RoutingPolicy(config),
        scheduler=Scheduler(repo, config),
        config=config,
        reasoner_label="heuristic",
        notifier=notifier,
        notifier_label=notifier.label,
    )


def test_service_dispatches_notification_on_emergency_escalation(tmp_path) -> None:
    notifier = _SpyNotifier()
    service = _build_service(tmp_path, notifier)
    outcome = service.process_intake(
        phone="555-111-2222",
        age=58,
        sex="Male",
        symptoms="Chest pain and shortness of breath since morning",
        auto_book_high_urgency=False,
        always_route_when_model_requests_human=True,
    )
    assert outcome.routing_decision.action == RoutingAction.ESCALATE
    assert outcome.queue_id is not None
    assert len(notifier.events) == 1
    assert notifier.events[0].urgency == "EMERGENCY"

    audit = service.repository.recent_audit_log(limit=50)
    actions = [row["action"] for row in audit]
    assert "NOTIFICATION_DISPATCHED" in actions


def test_audit_views_are_role_scoped(tmp_path) -> None:
    notifier = _SpyNotifier()
    service = _build_service(tmp_path, notifier)
    service.process_intake(
        phone="5551239876",
        age=26,
        sex="Female",
        symptoms="Cough and cold for two days",
        auto_book_high_urgency=True,
        always_route_when_model_requests_human=True,
    )

    operations = service.get_audit_view(role="operations", limit=20)
    assert operations["triage"]
    assert "symptoms" not in operations["triage"][0]
    assert "phone" not in operations["triage"][0]
    assert "payload" not in operations["audit_log"][0]

    nurse = service.get_audit_view(role="nurse", limit=20)
    assert nurse["triage"][0]["phone"] == "***-***-9876"
    assert "payload" in nurse["audit_log"][0]

    admin = service.get_audit_view(role="admin", limit=20)
    assert admin["triage"][0]["phone"] == "5551239876"
