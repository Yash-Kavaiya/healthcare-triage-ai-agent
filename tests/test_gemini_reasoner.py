import json

import triage_agent.reasoner_factory as reasoner_factory
from triage_agent.config import TriageConfig
from triage_agent.gemini_reasoner import GeminiTriageReasoner
from triage_agent.llm_reasoner import HybridTriageReasoner
from triage_agent.models import Urgency


def _payload_json() -> str:
    payload = {
        "urgency": "SOON",
        "confidence": 0.83,
        "red_flags": [],
        "department_candidates": [
            {"department": "General Medicine", "score": 0.7},
            {"department": "Dermatology", "score": 0.3},
        ],
        "suggested_department": "General Medicine",
        "rationale": "Symptoms look non-acute and can be reviewed soon.",
        "recommended_timeframe_minutes": 720,
        "human_routing_flag": False,
    }
    return json.dumps(payload)


class _GeminiResponse:
    def __init__(self, text: str):
        self.text = text


class _GeminiModels:
    def __init__(self, text: str):
        self._text = text

    def generate_content(self, **kwargs):
        return _GeminiResponse(self._text)


class _GeminiClient:
    def __init__(self, text: str):
        self.models = _GeminiModels(text)


class _StubGeminiReasoner:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def analyze(self, *, age: int, sex: str, symptoms: str):
        raise NotImplementedError


def test_gemini_reasoner_parses_json_response() -> None:
    reasoner = GeminiTriageReasoner(client=_GeminiClient(_payload_json()))
    result = reasoner.analyze(age=22, sex="Female", symptoms="Mild rash for two days")
    assert result.urgency == Urgency.SOON
    assert result.suggested_department == "General Medicine"
    assert result.human_routing_flag is False


def test_gemini_reasoner_parses_fenced_json() -> None:
    fenced = f"```json\n{_payload_json()}\n```"
    reasoner = GeminiTriageReasoner(client=_GeminiClient(fenced))
    result = reasoner.analyze(age=30, sex="Male", symptoms="Dry skin and mild irritation")
    assert result.urgency == Urgency.SOON
    assert result.recommended_timeframe_minutes == 720


def test_factory_builds_gemini_reasoner(monkeypatch) -> None:
    monkeypatch.setattr(reasoner_factory, "GeminiTriageReasoner", _StubGeminiReasoner)
    cfg = TriageConfig(reasoner_mode="gemini", gemini_model="gemini-3-flash-preview")
    reasoner, label = reasoner_factory.build_reasoner(cfg)
    assert isinstance(reasoner, _StubGeminiReasoner)
    assert label == "gemini:gemini-3-flash-preview"


def test_factory_builds_hybrid_gemini_reasoner(monkeypatch) -> None:
    monkeypatch.setattr(reasoner_factory, "GeminiTriageReasoner", _StubGeminiReasoner)
    cfg = TriageConfig(reasoner_mode="hybrid-gemini", gemini_model="gemini-3-flash-preview")
    reasoner, label = reasoner_factory.build_reasoner(cfg)
    assert isinstance(reasoner, HybridTriageReasoner)
    assert isinstance(reasoner.primary, _StubGeminiReasoner)
    assert label == "hybrid(gemini:gemini-3-flash-preview->heuristic)"
