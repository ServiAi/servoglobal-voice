from __future__ import annotations

import asyncio
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.crm.infrastructure.models import CrmVoiceCall
from app.modules.voice.domain.errors import VoiceSessionError, VoiceSessionNotFoundError
from app.modules.voice.infrastructure.livekit_runtime import RuntimeDispatchResult
from app.modules.voice.infrastructure.models import VoiceSession
from app.modules.voice.public import VoiceSessionFacade, WebRTCJoinInfo


class _Backend:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        if self.fail:
            raise RuntimeError("boom")
        self.calls += 1
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

    async def close_session_room(self, session_id: str) -> None: ...


class WebRTCJoinTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        for name, value in (
            ("LIVEKIT_URL", "wss://livekit.example"),
            ("LIVEKIT_API_KEY", "test-key"),
            ("LIVEKIT_API_SECRET", "s" * 32),
        ):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=self.tenant.id, name="Join agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=self.tenant.id, agent_id=agent.id, version=1, status="published", language="es",
                timezone="America/Bogota", identity_json={"name": "Join agent"},
                instructions_json={"system_prompt": "x"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.status, agent.published_version_id = "active", version.id
            db.commit()
            self.agent_id, self.version_id = agent.id, version.id

    def _session(self, key: str = "k1", channel: str = "webrtc") -> str:
        with SessionLocal() as db:
            return VoiceSessionFacade(db).create_session_from_agent_version(
                self.tenant.id, self.agent_id, self.version_id, channel=channel, direction="internal",
                idempotency_key=key,
            ).session_id

    def _crm_call(self, tenant_id: str | None = None) -> str:
        with SessionLocal() as db:
            call = CrmVoiceCall(tenant_id=tenant_id or self.tenant.id, provider="ultravox", direction="webrtc", status="requested")
            db.add(call)
            db.commit()
            return call.id

    def _join(self, session_id: str, backend: _Backend, tenant_id: str | None = None) -> WebRTCJoinInfo:
        with SessionLocal() as db:
            return asyncio.run(
                VoiceSessionFacade(db, runtime_backend=backend).ensure_webrtc_join(session_id, tenant_id or self.tenant.id)
            )

    def test_ensure_join_dispatches_once_and_replays_only_mint_new_tokens(self) -> None:
        session_id, backend = self._session(), _Backend()
        first, second = self._join(session_id, backend), self._join(session_id, backend)

        self.assertEqual(backend.calls, 1)
        self.assertEqual(first.room_name, second.room_name)
        self.assertEqual(first.room_name, f"sg-vs-{session_id}")
        self.assertNotEqual(first.participant_token, second.participant_token)
        self.assertEqual((first.server_url, first.voice_session_id), ("wss://livekit.example", session_id))
        with SessionLocal() as db:
            self.assertEqual(db.get(VoiceSession, session_id).status, "dispatched")

    def test_ensure_join_reports_dispatch_failure_and_terminal_sessions(self) -> None:
        failing = self._session("fails")
        with self.assertRaisesRegex(VoiceSessionError, "voice_session_dispatch_failed"):
            self._join(failing, _Backend(fail=True))
        with self.assertRaisesRegex(VoiceSessionError, "voice_session_dispatch_failed"):
            self._join(failing, _Backend())  # failed is terminal for good: no second room

        ended = self._session("ended")
        backend = _Backend()
        self._join(ended, backend)
        with SessionLocal() as db:
            db.get(VoiceSession, ended).status = "ended"
            db.commit()
        with self.assertRaisesRegex(VoiceSessionError, "voice_session_terminal"):
            self._join(ended, backend)
        self.assertEqual(backend.calls, 1)

    def test_unconfigured_transport_is_detected_before_dispatch_and_leaves_the_session_requested(self) -> None:
        session_id, backend = self._session("preflight"), _Backend()
        for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
            with self.subTest(missing=name), patch.object(settings, name, ""):
                with self.assertRaisesRegex(VoiceSessionError, "^voice_webrtc_not_configured$"):
                    self._join(session_id, backend)
                with SessionLocal() as db:
                    self.assertEqual(db.get(VoiceSession, session_id).status, "requested")
        self.assertEqual(backend.calls, 0)
        self.assertEqual(self._join(session_id, backend).room_name, f"sg-vs-{session_id}")  # recovers once configured
        self.assertEqual(backend.calls, 1)

    def test_ensure_join_refuses_non_webrtc_and_foreign_tenant_sessions(self) -> None:
        with self.assertRaises(VoiceSessionError):
            self._join(self._session("sip", channel="sip"), _Backend())
        with self.assertRaises(VoiceSessionNotFoundError):
            self._join(self._session("mine"), _Backend(), tenant_id="another-tenant")

    def test_attach_crm_call_is_idempotent_tenant_scoped_and_rejects_a_different_call(self) -> None:
        session_id, call_id = self._session(), self._crm_call()
        with SessionLocal() as db:
            facade = VoiceSessionFacade(db)
            facade.attach_crm_call(session_id, self.tenant.id, call_id)
            facade.attach_crm_call(session_id, self.tenant.id, call_id)
            with self.assertRaisesRegex(VoiceSessionError, "crm_voice_call_conflict"):
                facade.attach_crm_call(session_id, self.tenant.id, self._crm_call())
            with self.assertRaisesRegex(VoiceSessionError, "crm_voice_call_not_found"):
                facade.attach_crm_call(session_id, self.tenant.id, "missing")
            with self.assertRaisesRegex(VoiceSessionError, "crm_voice_call_not_found"):
                facade.attach_crm_call(session_id, "another-tenant", call_id)  # CRM call is not theirs
            with self.assertRaises(VoiceSessionNotFoundError):
                facade.attach_crm_call("missing-session", self.tenant.id, call_id)
            self.assertEqual(db.get(VoiceSession, session_id).crm_voice_call_id, call_id)


if __name__ == "__main__":
    import unittest

    unittest.main()
