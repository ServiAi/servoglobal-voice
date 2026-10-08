from __future__ import annotations

from datetime import datetime


class EvaluationExecutor:
    def __init__(self, repository: object) -> None:
        self.repository = repository

    def claim_batch(self, *, now: datetime, lease_seconds: int, batch_size: int) -> list[dict]:
        return self.repository.claim_batch(now=now, lease_seconds=lease_seconds, batch_size=batch_size)

    def execute(self, claim: dict, *, now: datetime | None = None) -> bool:
        return self.repository.execute(claim, now=now)
