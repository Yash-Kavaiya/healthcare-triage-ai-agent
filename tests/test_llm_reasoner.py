import json

from triage_agent.llm_reasoner import (
    HybridTriageReasoner,
    LLMTriagePayload,
    OpenAITriageReasoner,
)
from triage_agent.models import Urgency
from triage_agent.reasoner import HeuristicTriageReasoner


class _ResponseEnvelope:
    def __init__(self, parsed=None, output_text: str = ""):
        self.output_parsed = parsed
        self.output_text = output_text


class _ResponsesAPIParseOK:
    def parse(self, **kwargs):
        payload = LLMTriagePayload(
            urgency="SOON",
            confidence=0.81,
            red_flags=[],
            department_candidates=[
                {"department": "General Medicine", "score": 0.8},
                {"department": "Pulmonology", "score": 0.2},
            ],
            suggested_department="General Medicine",
            rationale="Mild respiratory symptoms without immediate danger signs.",
            recommended_timeframe_minutes=120,
            human_routing_flag=False,
        )
        return _ResponseEnvelope(parsed=payload)


class _ResponsesAPIFallback:
    def parse(self, **kwargs):
        raise RuntimeError("parse unavailable")

    def create(self, **kwargs):
        payload = {
            "urgency": "URGENT",
            "confidence": 0.87,
            "red_flags": ["Respiratory compromise risk"],
            "department_candidates": [
                {"department": "Pulmonology", "score": 0.9},
                {"department": "General Medicine", "score": 0.1},
            ],
            "suggested_department": "Pulmonology",
            "rationale": "Breathing symptoms with red-flag concern.",
            "recommended_timeframe_minutes": 90,
            "human_routing_flag": True,
        }
        return _ResponseEnvelope(output_text=json.dumps(payload))


class _ClientParseOK:
    def __init__(self):
        self.responses = _ResponsesAPIParseOK()


class _ClientFallback:
    def __init__(self):
        self.responses = _ResponsesAPIFallback()


class _FailingReasoner:
    def analyze(self, *, age: int, sex: str, symptoms: str):
        raise RuntimeError("LLM outage")


def test_openai_reasoner_uses_parse_path() -> None:
    reasoner = OpenAITriageReasoner(client=_ClientParseOK())
    result = reasoner.analyze(age=28, sex="Female", symptoms="Cough and mild fever")
    assert result.urgency == Urgency.SOON
    assert result.suggested_department == "General Medicine"
    assert result.human_routing_flag is False


def test_openai_reasoner_falls_back_to_json_schema_create() -> None:
    reasoner = OpenAITriageReasoner(client=_ClientFallback())
    result = reasoner.analyze(
        age=61,
        sex="Male",
        symptoms="Breathing feels heavy and shortness of breath",
    )
    assert result.urgency == Urgency.URGENT
    assert result.suggested_department == "Pulmonology"
    assert result.human_routing_flag is True


def test_hybrid_reasoner_uses_safe_fallback() -> None:
    hybrid = HybridTriageReasoner(
        primary=_FailingReasoner(),
        fallback=HeuristicTriageReasoner(),
    )
    result = hybrid.analyze(
        age=42,
        sex="Other",
        symptoms="cough and cold",
    )
    assert result.human_routing_flag is True
    assert result.confidence <= 0.79
    assert "Fallback reasoner used" in result.rationale
