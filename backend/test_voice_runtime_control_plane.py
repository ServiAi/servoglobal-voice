from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.agents import TenantAgent, TenantAgentVersion
from app.security.voice_runtime_auth import create_runtime_token, require_voice_runtime
from app.services.livekit_runtime_backend import RuntimeDispatchResult
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.voice_session_service import VoiceSessionService


class FakeBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        self.calls += 1
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")


class VoiceRuntimeControlPlaneTests(Integration2ATestCase):
    def _session(self):
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=self.tenant.id, name="Runtime agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=self.tenant.id, agent_id=agent.id, version=1, status="published", language="es-CO", timezone="America/Bogota",
                identity_json={"name": "Runtime agent"}, instructions_json={"system_prompt": "Published"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.status = "active"
            agent.published_version_id = version.id
            db.commit()
            return agent.id

    def test_short_lived_runtime_jwt(self) -> None:
        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            token = create_runtime_token()
            self.assertIsNone(require_voice_runtime(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)))

    def test_wrong_audience_is_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            token = jwt.encode({"iss": settings.VOICE_RUNTIME_JWT_ISSUER, "aud": "wrong", "sub": "voice-runtime", "iat": now, "exp": now + timedelta(seconds=60)}, "x" * 32, algorithm="HS256")
            with self.assertRaises(HTTPException):
                require_voice_runtime(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))

    def test_dispatch_is_idempotent_and_persists_correlations(self) -> None:
        agent_id = self._session()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            backend = FakeBackend()
            dispatcher = VoiceRuntimeDispatcher(db, backend)
            import asyncio
            asyncio.run(dispatcher.dispatch(session))
            asyncio.run(dispatcher.dispatch(session))
            self.assertEqual(backend.calls, 1)
            self.assertEqual(session.livekit_room_name, f"sg-vs-{session.id}")
            self.assertEqual(session.livekit_dispatch_id, "dispatch-1")
            self.assertEqual(session.status, "dispatched")


if __name__ == "__main__":
    unittest.main()
