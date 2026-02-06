from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import DepartmentScore, TriageResult, Urgency
from .pii import redact_pii
from .reasoner_protocol import TriageReasoner

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


SYSTEM_PROMPT = """
You are a healthcare triage assistant.
Return only data that conforms to the schema.
Use conservative safety-first judgment:
- Prefer higher urgency when uncertain.
- Set human_routing_flag=true on ambiguity, conflicting cues, or low certainty.
- Provide concise rationale grounded in symptoms and context.
Urgency values must be one of: EMERGENCY, URGENT, SOON, ROUTINE.
Department candidates should be scored from 0.0 to 1.0 and sorted descending.
""".strip()


class LLMDepartmentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str = Field(min_length=1, max_length=80)
    score: float = Field(ge=0.0, le=1.0)


class LLMTriagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urgency: Literal["EMERGENCY", "URGENT", "SOON", "ROUTINE"]
    confidence: float = Field(ge=0.0, le=1.0)
    red_flags: list[str] = Field(default_factory=list, max_length=20)
    department_candidates: list[LLMDepartmentCandidate] = Field(
        default_factory=list,
        max_length=8,
    )
    suggested_department: str = Field(min_length=1, max_length=80)
    rationale: str = Field(min_length=5, max_length=1200)
    recommended_timeframe_minutes: int = Field(ge=1, le=60 * 24 * 30)
    human_routing_flag: bool


class LLMReasonerError(RuntimeError):
    pass


@dataclass
class OpenAITriageReasoner:
    model: str = "gpt-4o-mini"
    max_output_tokens: int = 500
    request_timeout_seconds: float = 20.0
    api_key: str | None = None
    client: Any | None = None

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        if OpenAI is None:
            raise ImportError(
                "openai package is not installed. Install dependencies from requirements.txt."
            )
        self.client = OpenAI(
            api_key=self.api_key,
            timeout=self.request_timeout_seconds,
        )

    def analyze(self, *, age: int, sex: str, symptoms: str) -> TriageResult:
        redacted = redact_pii(symptoms)
        request_input = self._build_input(age=age, sex=sex, redacted_symptoms=redacted)

        payload: LLMTriagePayload | None = None
        try:
            payload = self._parse_via_sdk_parser(request_input)
        except Exception as exc:
            logger.warning("OpenAI parser path failed: %s", exc)
            try:
                payload = self._parse_via_strict_json_schema(request_input)
            except Exception as strict_exc:
                raise LLMReasonerError(
                    f"OpenAI structured triage failed: {strict_exc}"
                ) from strict_exc

        return self._to_result(redacted_symptoms=redacted, payload=payload)

    def _build_input(
        self, *, age: int, sex: str, redacted_symptoms: str
    ) -> list[dict[str, Any]]:
        user_payload = {
            "age": age,
            "sex": sex,
            "symptoms": redacted_symptoms,
            "task": "Generate structured triage output only.",
        }
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ]

    def _parse_via_sdk_parser(self, request_input: list[dict[str, Any]]) -> LLMTriagePayload:
        response = self.client.responses.parse(
            model=self.model,
            input=request_input,
            text_format=LLMTriagePayload,
            max_output_tokens=self.max_output_tokens,
        )
        payload = getattr(response, "output_parsed", None)
        if payload is None:
            raise LLMReasonerError("responses.parse returned no output_parsed payload.")
        if isinstance(payload, LLMTriagePayload):
            return payload
        return LLMTriagePayload.model_validate(payload)

    def _parse_via_strict_json_schema(
        self, request_input: list[dict[str, Any]]
    ) -> LLMTriagePayload:
        response = self.client.responses.create(
            model=self.model,
            input=request_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "triage_output",
                    "schema": LLMTriagePayload.model_json_schema(),
                    "strict": True,
                }
            },
            max_output_tokens=self.max_output_tokens,
        )
        output_text = getattr(response, "output_text", "")
        if not output_text:
            raise LLMReasonerError("responses.create returned empty output_text.")
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise LLMReasonerError("Model output was not valid JSON.") from exc
        try:
            return LLMTriagePayload.model_validate(data)
        except ValidationError as exc:
            raise LLMReasonerError(f"Schema validation failed: {exc}") from exc

    def _to_result(
        self, *, redacted_symptoms: str, payload: LLMTriagePayload
    ) -> TriageResult:
        urgency = Urgency(payload.urgency)
        candidates = self._normalize_candidates(
            payload.department_candidates,
            fallback_department=payload.suggested_department,
        )
        suggested = payload.suggested_department.strip() or candidates[0].department
        if suggested not in {c.department for c in candidates}:
            candidates.append(DepartmentScore(department=suggested, score=0.2))
            candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        timeframe = max(
            1,
            min(payload.recommended_timeframe_minutes, self._default_window(urgency)),
        )
        red_flags = sorted({item.strip() for item in payload.red_flags if item.strip()})[:20]
        rationale = payload.rationale.strip()

        return TriageResult(
            redacted_symptoms=redacted_symptoms,
            urgency=urgency,
            confidence=round(float(payload.confidence), 2),
            red_flags=red_flags,
            department_candidates=candidates,
            suggested_department=suggested,
            rationale=rationale,
            recommended_timeframe_minutes=timeframe,
            human_routing_flag=bool(payload.human_routing_flag),
        )

    @staticmethod
    def _normalize_candidates(
        raw: list[LLMDepartmentCandidate], fallback_department: str
    ) -> list[DepartmentScore]:
        cleaned: list[DepartmentScore] = []
        for item in raw:
            name = item.department.strip()
            if not name:
                continue
            cleaned.append(DepartmentScore(department=name, score=round(float(item.score), 3)))

        if not cleaned:
            default_name = fallback_department.strip() or "General Medicine"
            return [DepartmentScore(department=default_name, score=1.0)]

        merged: dict[str, float] = {}
        for item in cleaned:
            merged[item.department] = max(item.score, merged.get(item.department, 0.0))
        total = sum(merged.values())
        if total <= 0:
            total = float(len(merged))
            merged = {key: 1.0 for key in merged}
        normalized = [
            DepartmentScore(department=dept, score=round(score / total, 3))
            for dept, score in merged.items()
        ]
        normalized.sort(key=lambda d: d.score, reverse=True)
        return normalized

    @staticmethod
    def _default_window(urgency: Urgency) -> int:
        return {
            Urgency.EMERGENCY: 30,
            Urgency.URGENT: 240,
            Urgency.SOON: 1440,
            Urgency.ROUTINE: 10080,
        }[urgency]


@dataclass
class HybridTriageReasoner:
    primary: TriageReasoner
    fallback: TriageReasoner

    def analyze(self, *, age: int, sex: str, symptoms: str) -> TriageResult:
        try:
            return self.primary.analyze(age=age, sex=sex, symptoms=symptoms)
        except Exception as exc:
            logger.exception("Primary reasoner failed; switching to fallback. Error: %s", exc)
            fallback_result = self.fallback.analyze(age=age, sex=sex, symptoms=symptoms)
            fallback_result.human_routing_flag = True
            fallback_result.confidence = min(fallback_result.confidence, 0.79)
            fallback_result.rationale = (
                fallback_result.rationale
                + " Fallback reasoner used because LLM structured output failed."
            )
            return fallback_result
