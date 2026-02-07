from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .llm_reasoner import (
    LLMDepartmentCandidate,
    LLMReasonerError,
    LLMTriagePayload,
    SYSTEM_PROMPT,
)
from .models import DepartmentScore, TriageResult, Urgency
from .pii import redact_pii

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover
    genai = None  # type: ignore[assignment]
    genai_types = None  # type: ignore[assignment]


@dataclass
class GeminiTriageReasoner:
    model: str = "gemini-3-flash-preview"
    max_output_tokens: int = 500
    request_timeout_seconds: float = 20.0
    thinking_level: str = "HIGH"
    api_key: str | None = None
    client: Any | None = None

    def __post_init__(self) -> None:
        if self.client is not None:
            return
        if genai is None:
            raise ImportError(
                "google-genai package is not installed. Install dependencies from requirements.txt."
            )
        self.client = genai.Client(api_key=self.api_key)

    def analyze(self, *, age: int, sex: str, symptoms: str) -> TriageResult:
        redacted = redact_pii(symptoms)
        prompt = self._build_prompt(age=age, sex=sex, redacted_symptoms=redacted)

        try:
            raw_output = self._generate_text(prompt)
            payload = self._parse_payload(raw_output)
        except Exception as exc:
            raise LLMReasonerError(f"Gemini structured triage failed: {exc}") from exc

        return self._to_result(redacted_symptoms=redacted, payload=payload)

    def _build_prompt(self, *, age: int, sex: str, redacted_symptoms: str) -> str:
        schema = LLMTriagePayload.model_json_schema()
        user_payload = {
            "age": age,
            "sex": sex,
            "symptoms": redacted_symptoms,
            "task": "Generate structured triage output only.",
        }
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "Return only valid JSON, no markdown.\n"
            "The JSON must strictly match this schema:\n"
            f"{json.dumps(schema, separators=(',', ':'))}\n\n"
            "Patient input:\n"
            f"{json.dumps(user_payload, separators=(',', ':'))}"
        )

    def _build_config(self) -> Any:
        base_config: dict[str, Any] = {
            "response_mime_type": "application/json",
            "max_output_tokens": self.max_output_tokens,
        }
        if self.thinking_level:
            base_config["thinking_config"] = {"thinking_level": self.thinking_level}

        if genai_types is None:
            return base_config

        try:
            thinking_config = None
            if self.thinking_level and hasattr(genai_types, "ThinkingConfig"):
                thinking_config = genai_types.ThinkingConfig(
                    thinking_level=self.thinking_level
                )
            return genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=self.max_output_tokens,
                thinking_config=thinking_config,
            )
        except Exception:
            return base_config

    def _generate_text(self, prompt: str) -> str:
        config = self._build_config()
        last_error: Exception | None = None

        for contents in (prompt, [prompt]):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                text = self._extract_text(response)
                if text.strip():
                    return text
            except TypeError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        raise LLMReasonerError("Gemini returned no text output.")

    def _extract_text(self, response: Any) -> str:
        direct = getattr(response, "text", None)
        if isinstance(direct, str) and direct.strip():
            return direct

        if isinstance(response, dict):
            text_value = response.get("text")
            if isinstance(text_value, str) and text_value.strip():
                return text_value

        chunks: list[str] = []
        candidates = getattr(response, "candidates", None)
        if candidates:
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) if content is not None else None
                if not parts:
                    continue
                for part in parts:
                    part_text = getattr(part, "text", None)
                    if isinstance(part_text, str) and part_text.strip():
                        chunks.append(part_text)
        return "\n".join(chunks)

    def _parse_payload(self, raw_output: str) -> LLMTriagePayload:
        cleaned = raw_output.strip()
        fence_match = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*)\s*```$", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        data: Any
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end <= start:
                raise LLMReasonerError("Model output was not valid JSON.")
            try:
                data = json.loads(cleaned[start : end + 1])
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
