from __future__ import annotations

from dataclasses import dataclass

from .models import DepartmentScore, TriageResult, Urgency
from .pii import redact_pii


@dataclass
class HeuristicTriageReasoner:
    """Deterministic triage reasoner that mimics structured LLM output."""

    emergency_terms: tuple[str, ...] = (
        "chest pain",
        "chest feels tight",
        "shortness of breath",
        "difficulty breathing",
        "breathing feels heavy",
        "severe bleeding",
        "fainting",
        "loss of consciousness",
        "slurred speech",
        "one-sided weakness",
        "seizure",
        "suicidal",
    )
    urgent_terms: tuple[str, ...] = (
        "high fever",
        "persistent fever",
        "vomiting",
        "blood pressure",
        "palpitations",
        "severe headache",
        "asthma flare",
        "wheezing",
        "dehydration",
        "dizzy and weak",
        "dizziness",
    )
    soon_terms: tuple[str, ...] = (
        "cough",
        "cold",
        "sore throat",
        "mild fever",
        "rash",
        "back pain",
        "joint pain",
        "stomach pain",
        "abdominal pain",
        "fatigue",
        "nausea",
    )
    uncertainty_terms: tuple[str, ...] = (
        "not sure",
        "maybe",
        "kind of",
        "unsure",
        "hard to describe",
        "on and off",
    )
    red_flag_map: dict[str, str] = None  # type: ignore[assignment]
    department_keywords: dict[str, tuple[str, ...]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.red_flag_map is None:
            self.red_flag_map = {
                "chest pain": "Possible cardiac emergency",
                "shortness of breath": "Respiratory compromise risk",
                "difficulty breathing": "Respiratory compromise risk",
                "loss of consciousness": "Neurologic emergency risk",
                "slurred speech": "Possible stroke signs",
                "one-sided weakness": "Possible stroke signs",
                "severe bleeding": "Hemorrhage risk",
                "suicidal": "Immediate mental health safety concern",
            }
        if self.department_keywords is None:
            self.department_keywords = {
                "Cardiology": (
                    "chest pain",
                    "palpitations",
                    "heart",
                    "blood pressure",
                    "tight chest",
                ),
                "Pulmonology": (
                    "breathing",
                    "shortness of breath",
                    "wheezing",
                    "cough",
                    "asthma",
                ),
                "Neurology": (
                    "headache",
                    "dizziness",
                    "fainting",
                    "slurred speech",
                    "weakness",
                    "seizure",
                ),
                "Orthopedics": (
                    "fracture",
                    "sprain",
                    "joint pain",
                    "back pain",
                    "muscle",
                ),
                "Dermatology": ("rash", "skin", "itching", "eczema"),
                "Gastroenterology": (
                    "abdominal pain",
                    "stomach",
                    "diarrhea",
                    "vomiting",
                    "nausea",
                ),
            }

    def analyze(self, *, age: int, sex: str, symptoms: str) -> TriageResult:
        redacted = redact_pii(symptoms)
        normalized = redacted.lower().strip()

        red_flags = self._detect_red_flags(normalized)
        urgency = self._derive_urgency(normalized, age, red_flags)
        department_candidates = self._score_departments(normalized)
        top_score = department_candidates[0].score if department_candidates else 0.0
        confidence = self._estimate_confidence(
            normalized=normalized,
            urgency=urgency,
            top_department_score=top_score,
        )
        human_flag = self._needs_human_routing(
            normalized=normalized,
            confidence=confidence,
            top_department_score=top_score,
            red_flags=red_flags,
        )
        rationale = self._build_rationale(
            normalized=normalized,
            urgency=urgency,
            red_flags=red_flags,
            department_candidates=department_candidates,
            age=age,
            sex=sex,
        )

        return TriageResult(
            redacted_symptoms=redacted,
            urgency=urgency,
            confidence=confidence,
            red_flags=red_flags,
            department_candidates=department_candidates,
            suggested_department=department_candidates[0].department,
            rationale=rationale,
            recommended_timeframe_minutes=self._recommended_window(urgency),
            human_routing_flag=human_flag,
        )

    def _detect_red_flags(self, normalized: str) -> list[str]:
        flags = []
        for phrase, flag in self.red_flag_map.items():
            if phrase in normalized:
                flags.append(flag)
        return sorted(set(flags))

    def _derive_urgency(self, normalized: str, age: int, red_flags: list[str]) -> Urgency:
        if red_flags:
            return Urgency.EMERGENCY
        if any(term in normalized for term in self.emergency_terms):
            return Urgency.EMERGENCY
        if any(term in normalized for term in self.urgent_terms):
            return Urgency.URGENT
        if any(term in normalized for term in self.soon_terms):
            if age >= 70 and ("dizziness" in normalized or "fever" in normalized):
                return Urgency.URGENT
            return Urgency.SOON
        return Urgency.ROUTINE

    def _score_departments(self, normalized: str) -> list[DepartmentScore]:
        raw_scores: dict[str, float] = {}
        for department, keywords in self.department_keywords.items():
            hits = sum(1 for kw in keywords if kw in normalized)
            if hits > 0:
                raw_scores[department] = float(hits)

        if not raw_scores:
            raw_scores["General Medicine"] = 1.0
        else:
            raw_scores["General Medicine"] = 0.35

        total = sum(raw_scores.values())
        ranked = sorted(
            (
                DepartmentScore(department=dept, score=round(score / total, 3))
                for dept, score in raw_scores.items()
            ),
            key=lambda d: d.score,
            reverse=True,
        )
        return ranked

    def _estimate_confidence(
        self,
        *,
        normalized: str,
        urgency: Urgency,
        top_department_score: float,
    ) -> float:
        base_map = {
            Urgency.EMERGENCY: 0.92,
            Urgency.URGENT: 0.84,
            Urgency.SOON: 0.78,
            Urgency.ROUTINE: 0.72,
        }
        confidence = base_map[urgency]
        if len(normalized) < 20:
            confidence -= 0.08
        if any(term in normalized for term in self.uncertainty_terms):
            confidence -= 0.15
        if top_department_score < 0.60:
            confidence -= 0.08
        if top_department_score > 0.85:
            confidence += 0.04
        return round(max(0.30, min(0.99, confidence)), 2)

    def _needs_human_routing(
        self,
        *,
        normalized: str,
        confidence: float,
        top_department_score: float,
        red_flags: list[str],
    ) -> bool:
        if any(term in normalized for term in self.uncertainty_terms):
            return True
        if confidence < 0.72:
            return True
        if top_department_score < 0.60:
            return True
        if len(red_flags) >= 2:
            return False
        return False

    def _build_rationale(
        self,
        *,
        normalized: str,
        urgency: Urgency,
        red_flags: list[str],
        department_candidates: list[DepartmentScore],
        age: int,
        sex: str,
    ) -> str:
        key_findings = []
        for term in self.emergency_terms + self.urgent_terms + self.soon_terms:
            if term in normalized:
                key_findings.append(term)
            if len(key_findings) == 3:
                break

        detail = ", ".join(key_findings) if key_findings else "non-specific symptoms"
        department = department_candidates[0].department
        rationale = (
            f"Classified as {urgency.value} from symptom pattern ({detail}); "
            f"best-matched department is {department}."
        )
        if red_flags:
            rationale += f" Red flags: {', '.join(red_flags)}."
        if age >= 65:
            rationale += " Older age used as additional risk context."
        if sex:
            rationale += f" Sex recorded as {sex} for downstream clinical review."
        return rationale

    @staticmethod
    def _recommended_window(urgency: Urgency) -> int:
        return {
            Urgency.EMERGENCY: 30,
            Urgency.URGENT: 240,
            Urgency.SOON: 1440,
            Urgency.ROUTINE: 10080,
        }[urgency]
