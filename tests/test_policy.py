from triage_agent.config import TriageConfig
from triage_agent.models import DepartmentScore, RoutingAction, TriageResult, Urgency
from triage_agent.policy import RoutingPolicy


def _triage_result(
    *,
    urgency: Urgency = Urgency.SOON,
    confidence: float = 0.90,
    dept_score: float = 0.90,
    human_flag: bool = False,
) -> TriageResult:
    return TriageResult(
        redacted_symptoms="cough",
        urgency=urgency,
        confidence=confidence,
        red_flags=[],
        department_candidates=[DepartmentScore("General Medicine", dept_score)],
        suggested_department="General Medicine",
        rationale="test",
        recommended_timeframe_minutes=60,
        human_routing_flag=human_flag,
    )


def test_policy_auto_books_when_all_thresholds_met() -> None:
    policy = RoutingPolicy(TriageConfig())
    decision = policy.decide(_triage_result())
    assert decision.action == RoutingAction.AUTO_BOOK


def test_policy_routes_queue_when_confidence_low() -> None:
    policy = RoutingPolicy(TriageConfig())
    decision = policy.decide(_triage_result(confidence=0.60, urgency=Urgency.SOON))
    assert decision.action == RoutingAction.QUEUE_REVIEW


def test_policy_escalates_emergency_when_human_routing_required() -> None:
    policy = RoutingPolicy(TriageConfig())
    decision = policy.decide(
        _triage_result(urgency=Urgency.EMERGENCY, confidence=0.95, human_flag=True)
    )
    assert decision.action == RoutingAction.ESCALATE
