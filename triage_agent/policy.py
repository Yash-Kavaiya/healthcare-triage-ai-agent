from __future__ import annotations

from dataclasses import dataclass

from .config import TriageConfig
from .models import RoutingAction, RoutingDecision, TriageResult, Urgency


@dataclass
class RoutingPolicy:
    config: TriageConfig

    def decide(
        self,
        triage_result: TriageResult,
        *,
        confidence_threshold: float | None = None,
        department_threshold: float | None = None,
        always_route_when_model_requests_human: bool | None = None,
        auto_book_high_urgency: bool | None = None,
    ) -> RoutingDecision:
        confidence_threshold = (
            self.config.auto_book_confidence_threshold
            if confidence_threshold is None
            else confidence_threshold
        )
        department_threshold = (
            self.config.department_score_threshold
            if department_threshold is None
            else department_threshold
        )
        always_route_when_model_requests_human = (
            self.config.always_route_when_model_requests_human
            if always_route_when_model_requests_human is None
            else always_route_when_model_requests_human
        )
        auto_book_high_urgency = (
            self.config.auto_book_high_urgency
            if auto_book_high_urgency is None
            else auto_book_high_urgency
        )

        if triage_result.urgency == Urgency.EMERGENCY and not auto_book_high_urgency:
            return RoutingDecision(
                action=RoutingAction.ESCALATE,
                reason="Emergency cases are configured for mandatory human escalation.",
                confidence_threshold=confidence_threshold,
                department_threshold=department_threshold,
            )

        if always_route_when_model_requests_human and triage_result.human_routing_flag:
            action = (
                RoutingAction.ESCALATE
                if triage_result.urgency == Urgency.EMERGENCY
                else RoutingAction.QUEUE_REVIEW
            )
            return RoutingDecision(
                action=action,
                reason="Model requested human routing.",
                confidence_threshold=confidence_threshold,
                department_threshold=department_threshold,
            )

        if triage_result.confidence < confidence_threshold:
            action = (
                RoutingAction.ESCALATE
                if triage_result.urgency == Urgency.EMERGENCY
                else RoutingAction.QUEUE_REVIEW
            )
            return RoutingDecision(
                action=action,
                reason="Confidence below policy threshold.",
                confidence_threshold=confidence_threshold,
                department_threshold=department_threshold,
            )

        if triage_result.top_department_score < department_threshold:
            return RoutingDecision(
                action=RoutingAction.QUEUE_REVIEW,
                reason="Department certainty below policy threshold.",
                confidence_threshold=confidence_threshold,
                department_threshold=department_threshold,
            )

        return RoutingDecision(
            action=RoutingAction.AUTO_BOOK,
            reason="All routing policy thresholds satisfied.",
            confidence_threshold=confidence_threshold,
            department_threshold=department_threshold,
        )
