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
from app.services.tenant_feature_service import TenantFeatureService, VOICE_RUNTIME_V2
from app.services.voice_session_service import VoiceSessionService


class FakeBackend:
    def __init__(self) -> None:
        self.calls = 0

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        self.calls += 1
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")


class VoiceRuntimeControlPlaneTests(Integration2ATestCase):
    def _session(self, tenant_id: str | None = None):
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Runtime agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id, agent_id=agent.id, version=1, status="published", language="es-CO", timezone="America/Bogota",
                identity_json={"name": "Runtime agent"}, instructions_json={"system_prompt": "Published"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.status = "active"
            agent.published_version_id = version.id
            db.commit()
            return agent.id

    def _dispatched_session(self, tenant_id: str | None = None):
        tenant_id = tenant_id or self.tenant.id
        agent_id = self._session(tenant_id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                tenant_id,
                agent_id,
                channel="webrtc",
                direction="internal",
            )
            session.livekit_room_name = f"sg-vs-{session.id}"
            session.status = "dispatched"
            db.commit()
            return session.id

    def _enable_runtime(self, tenant_id: str | None = None) -> None:
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                tenant_id or self.tenant.id,
                VOICE_RUNTIME_V2,
                True,
                {},
                self.user.id,
            )

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

    def test_webrtc_token_is_short_lived_room_scoped_and_microphone_only(self) -> None:
        self._enable_runtime()
        session_id = self._dispatched_session()
        with (
            patch.object(settings, "LIVEKIT_URL", "wss://livekit.example"),
            patch.object(settings, "LIVEKIT_API_KEY", "test-key"),
            patch.object(settings, "LIVEKIT_API_SECRET", "s" * 32),
            patch.object(settings, "VOICE_WEBRTC_TOKEN_TTL_SECONDS", 300),
        ):
            response = self.client.post(f"/api/v1/voice/sessions/{session_id}/webrtc-token")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["voice_session_id"], session_id)
        self.assertEqual(body["room_name"], f"sg-vs-{session_id}")
        self.assertEqual(body["server_url"], "wss://livekit.example")
        self.assertEqual(body["expires_in"], 300)
        self.assertNotIn("s" * 32, str(body))

        claims = jwt.decode(body["participant_token"], options={"verify_signature": False})
        self.assertTrue(claims["sub"].startswith("web-"))
        self.assertNotIn("@", claims["sub"])
        self.assertLessEqual(claims["exp"] - claims["nbf"], 300)
        self.assertEqual(
            claims["video"],
            {
                "roomCreate": False,
                "roomRecord": False,
                "roomAdmin": False,
                "roomJoin": True,
                "room": f"sg-vs-{session_id}",
                "canPublish": True,
                "canSubscribe": True,
                "canPublishData": False,
                "canPublishSources": ["microphone"],
                "canUpdateOwnMetadata": False,
                "ingressAdmin": False,
            },
        )
        self.assertNotIn("sip", claims)

    def test_webrtc_token_hides_cross_tenant_and_rejects_terminal_session(self) -> None:
        self._enable_runtime()
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="other@example.com")
        other_session_id = self._dispatched_session(other_tenant.id)
        self.assertEqual(
            self.client.post(f"/api/v1/voice/sessions/{other_session_id}/webrtc-token").status_code,
            404,
        )

        session_id = self._dispatched_session()
        with SessionLocal() as db:
            session = VoiceSessionService(db).get(session_id)
            session.status = "ended"
            db.commit()
        self.assertEqual(
            self.client.post(f"/api/v1/voice/sessions/{session_id}/webrtc-token").status_code,
            409,
        )

    def test_runtime_events_do_not_mark_connected_before_audio_is_proven(self) -> None:
        session_id = self._dispatched_session()
        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            token = create_runtime_token()
            headers = {"Authorization": f"Bearer {token}"}

            def post(event_id: str, event_type: str, payload: dict | None = None):
                return self.client.post(
                    f"/api/v1/internal/voice-runtime/sessions/{session_id}/events",
                    headers=headers,
                    json={
                        "spec_version": "1",
                        "event_id": event_id,
                        "session_id": session_id,
                        "event_type": event_type,
                        "source": "livekit",
                        "payload": payload or {},
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                )

            self.assertEqual(post("started", "voice.session.started").status_code, 200)
            self.assertEqual(post("ready", "voice.agent.ready").status_code, 200)
            self.assertEqual(
                post(
                    "participant",
                    "voice.participant.connected",
                    {"participant_identity": "web-random"},
                ).status_code,
                200,
            )
            with SessionLocal() as db:
                self.assertEqual(VoiceSessionService(db).get(session_id).status, "starting")

            self.assertEqual(
                post("transcript", "voice.transcript.final", {"speaker": "user", "text": "Hola"}).status_code,
                200,
            )
            self.assertEqual(post("connected", "voice.session.connected").status_code, 200)
            duplicate = post("connected", "voice.session.connected")
            self.assertEqual(duplicate.status_code, 200)
            self.assertTrue(duplicate.json()["duplicate"])
            self.assertEqual(
                post("ended", "voice.session.ended", {"end_reason": "participant_disconnected"}).status_code,
                200,
            )

        with SessionLocal() as db:
            session = VoiceSessionService(db).get(session_id)
            self.assertEqual(session.status, "ended")
            self.assertEqual(session.end_reason, "participant_disconnected")


if __name__ == "__main__":
    unittest.main()
