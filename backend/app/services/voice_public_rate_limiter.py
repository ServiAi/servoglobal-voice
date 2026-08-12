from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime, timedelta
from typing import Callable

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.identity import _uuid
from app.models.voice_submissions import VoicePublicRateLimitWindow


class VoicePublicRateLimitConfigurationError(RuntimeError):
    pass


def resolve_public_client_ip(request: Request, trust_cloudflare: bool) -> str:
    candidate = (
        request.headers.get("CF-Connecting-IP")
        if trust_cloudflare
        else request.client.host if request.client else ""
    )
    try:
        return str(ipaddress.ip_address((candidate or "").strip()))
    except ValueError:
        return "0.0.0.0"


def pseudonymize_ip(secret: str, normalized_ip: str) -> str:
    if not secret:
        raise VoicePublicRateLimitConfigurationError("rate limit hash secret missing")
    return hmac.new(secret.encode(), normalized_ip.encode(), hashlib.sha256).hexdigest()


class VoicePublicRateLimiter:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def consume(self, scope: str, limit: int, *, now: datetime | None = None) -> bool:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        window_start = current.replace(second=0, microsecond=0)
        with self.session_factory() as db:
            dialect = db.get_bind().dialect.name
            insert = sqlite_insert if dialect == "sqlite" else pg_insert
            statement = (
                insert(VoicePublicRateLimitWindow)
                .values(
                    id=_uuid(),
                    scope=scope,
                    window_start=window_start,
                    request_count=1,
                )
                .on_conflict_do_update(
                    index_elements=["scope", "window_start"],
                    set_={
                        "request_count": VoicePublicRateLimitWindow.request_count + 1
                    },
                )
                .returning(VoicePublicRateLimitWindow.request_count)
            )
            count = db.execute(statement).scalar_one()
            db.commit()
        return count <= limit

    def cleanup(
        self,
        *,
        now: datetime | None = None,
        retention_hours: int = 24,
        batch_size: int = 500,
    ) -> int:
        cutoff = (now or datetime.now(UTC)) - timedelta(hours=retention_hours)
        with self.session_factory() as db:
            ids = (
                select(VoicePublicRateLimitWindow.id)
                .where(VoicePublicRateLimitWindow.window_start < cutoff)
                .order_by(VoicePublicRateLimitWindow.window_start)
                .limit(batch_size)
            )
            result = db.execute(
                delete(VoicePublicRateLimitWindow).where(
                    VoicePublicRateLimitWindow.id.in_(ids)
                )
            )
            db.commit()
            return result.rowcount or 0
