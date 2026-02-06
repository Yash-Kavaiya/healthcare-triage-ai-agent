from __future__ import annotations

import logging
from dataclasses import dataclass

from .database import SQLiteRepository


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@dataclass
class Observability:
    repository: SQLiteRepository

    def snapshot(self) -> dict[str, int]:
        return self.repository.dashboard_metrics()
