from __future__ import annotations

from datetime import UTC, datetime, timedelta

from starlette.requests import Request

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.voice_submissions import VoicePublicRateLimitWindow
from app.services.voice_public_rate_limiter import (
    VoicePublicRateLimiter,
    pseudonymize_ip,
    resolve_public_client_ip,
)


class VoicePublicRateLimiterTests(Integration2ATestCase):
    def test_counter_is_durable_and_enforces_limit(self) -> None:
        limiter = VoicePublicRateLimiter(session_factory=SessionLocal)
        now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
        self.assertTrue(limiter.consume("global:hash", 2, now=now))
        self.assertTrue(limiter.consume("global:hash", 2, now=now))
        self.assertFalse(limiter.consume("global:hash", 2, now=now))
        with SessionLocal() as db:
            self.assertEqual(db.query(VoicePublicRateLimitWindow).one().request_count, 3)

    def test_cleanup_is_bounded_and_deterministic(self) -> None:
        limiter = VoicePublicRateLimiter(session_factory=SessionLocal)
        now = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
        for index in range(4):
            limiter.consume(f"old:{index}", 10, now=now - timedelta(hours=25))
        limiter.consume("current", 10, now=now)
        self.assertEqual(limiter.cleanup(now=now, batch_size=2), 2)
        with SessionLocal() as db:
            self.assertEqual(db.query(VoicePublicRateLimitWindow).count(), 3)

    def test_ip_hmac_and_cloudflare_trust_policy(self) -> None:
        digest = pseudonymize_ip("secret", "203.0.113.7")
        self.assertEqual(len(digest), 64)
        self.assertNotIn("203.0.113.7", digest)
        scope = {
            "type": "http",
            "headers": [(b"cf-connecting-ip", b"198.51.100.4"), (b"x-forwarded-for", b"192.0.2.9")],
            "client": ("203.0.113.7", 1234),
        }
        request = Request(scope)
        self.assertEqual(resolve_public_client_ip(request, False), "203.0.113.7")
        self.assertEqual(resolve_public_client_ip(request, True), "198.51.100.4")
