from __future__ import annotations

from typing import Protocol


class TurnstileVerificationPort(Protocol):
    async def verify(self, token: str | None, remote_ip: str) -> bool: ...
