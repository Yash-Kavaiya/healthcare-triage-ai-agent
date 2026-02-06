from __future__ import annotations

from typing import Protocol

from .models import TriageResult


class TriageReasoner(Protocol):
    def analyze(self, *, age: int, sex: str, symptoms: str) -> TriageResult:
        ...
