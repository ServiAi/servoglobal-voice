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
from app.models.crm import CrmContact, CrmLead, CrmPipelineStage
from app.schemas.integrations import VoiceProviderConfigRequest
from app.security.voice_runtime_auth import create_runtime_token, require_voice_runtime
from app.services.livekit_runtime_backend import RuntimeDispatchResult
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_runtime_dispatcher import VoiceRuntimeDispatcher
from app.services.tenant_feature_service import TenantFeatureService, VOICE_RUNTIME_V2
from app.services.voice_session_service import VoiceSessionService


class FakeBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.closed_sessions: list[str] = []

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        self.calls += 1
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

    async def close_session_room(self, session_id: str) -> None:
        self.closed_sessions.append(session_id)


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

    def _configure_ultravox(self, tenant_id: str, api_key: str, *, status: str = "active") -> None:
        with SessionLocal() as db:
            VoiceConfigService(db).upsert_provider_config(
                tenant_id,
                VoiceProviderConfigRequest(provider="ultravox", status=status, api_key=api_key),
            )

    def _get_credential(self, session_id: str, provider: str = "ultravox"):
        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            token = create_runtime_token()
            return self.client.get(
                f"/api/v1/internal/voice-runtime/sessions/{session_id}/credentials/{provider}",
                headers={"Authorization": f"Bearer {token}"},
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

    def test_dispatch_closes_room_if_agent_archived_while_livekit_accepts(self) -> None:
        import asyncio

        agent_id = self._session()

        class ArchiveDuringDispatch(FakeBackend):
            async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
                with SessionLocal() as other_db:
                    other_db.get(TenantAgent, agent_id).status = "archived"
                    other_db.commit()
                return await super().dispatch(session_id)

        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            backend = ArchiveDuringDispatch()
            asyncio.run(VoiceRuntimeDispatcher(db, backend).dispatch(session))
            self.assertEqual(session.status, "cancelled")
            self.assertEqual(backend.closed_sessions, [session.id])

    def test_runtime_credential_resolves_the_tenants_configured_key(self) -> None:
        self._configure_ultravox(self.tenant.id, "tenant-a-key")
        session_id = self._dispatched_session()

        response = self._get_credential(session_id)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"provider": "ultravox", "api_key": "tenant-a-key", "base_url": None})

    def test_runtime_credential_requires_valid_runtime_authentication(self) -> None:
        self._configure_ultravox(self.tenant.id, "tenant-a-key")
        session_id = self._dispatched_session()

        response = self.client.get(f"/api/v1/internal/voice-runtime/sessions/{session_id}/credentials/ultravox")

        self.assertEqual(response.status_code, 401)

    def test_runtime_credential_rejects_unknown_session(self) -> None:
        response = self._get_credential("00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 404)

    def test_runtime_credential_rejects_provider_not_bound_to_session(self) -> None:
        self._configure_ultravox(self.tenant.id, "tenant-a-key")
        session_id = self._dispatched_session()

        response = self._get_credential(session_id, provider="openai")

        self.assertEqual(response.status_code, 404)

    def test_runtime_credential_rejects_unsupported_provider(self) -> None:
        session_id = self._dispatched_session()

        response = self._get_credential(session_id, provider="not-a-real-provider")

        self.assertEqual(response.status_code, 422)

    def test_runtime_credential_rejects_inactive_integration(self) -> None:
        self._configure_ultravox(self.tenant.id, "tenant-a-key", status="inactive")
        session_id = self._dispatched_session()

        response = self._get_credential(session_id)

        self.assertEqual(response.status_code, 409)
        self.assertNotIn("tenant-a-key", response.text)

    def test_runtime_credential_rejects_configured_provider_without_api_key(self) -> None:
        from app.models.integrations import TenantVoiceProviderConfig

        with SessionLocal() as db:
            db.add(TenantVoiceProviderConfig(tenant_id=self.tenant.id, provider="ultravox", status="active"))
            db.commit()
        session_id = self._dispatched_session()

        response = self._get_credential(session_id)

        self.assertEqual(response.status_code, 409)

    def test_runtime_credential_rejects_terminal_session(self) -> None:
        self._configure_ultravox(self.tenant.id, "tenant-a-key")
        session_id = self._dispatched_session()
        with SessionLocal() as db:
            VoiceSessionService(db).get(session_id).status = "ended"
            db.commit()

        response = self._get_credential(session_id)

        self.assertEqual(response.status_code, 409)

    def test_runtime_credential_is_isolated_per_tenant(self) -> None:
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="tenant-b@example.com")
        self._configure_ultravox(self.tenant.id, "tenant-a-key")
        self._configure_ultravox(other_tenant.id, "tenant-b-key")
        session_a = self._dispatched_session(self.tenant.id)
        session_b = self._dispatched_session(other_tenant.id)

        response_a = self._get_credential(session_a)
        response_b = self._get_credential(session_b)

        self.assertEqual(response_a.json()["api_key"], "tenant-a-key")
        self.assertEqual(response_b.json()["api_key"], "tenant-b-key")
        self.assertNotEqual(response_a.json()["api_key"], response_b.json()["api_key"])

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


class AgentToolInvokeEndpointTests(Integration2ATestCase):
    """POST /api/v1/internal/voice-runtime/sessions/{id}/tools/{key}/invoke.
    Same internal-runtime trust boundary as /spec and /events (see
    VoiceRuntimeControlPlaneTests above); this endpoint additionally
    re-resolves the session's own published tool binding from the database
    rather than trusting anything the caller (voice-runtime) asserts about
    which tools are bound -- see ToolDispatchService."""

    def _session_with_tools(
        self,
        tools: list[dict],
        tenant_id: str | None = None,
        *,
        lead_id: str | None = None,
        contact_id: str | None = None,
        caller_phone: str | None = None,
    ) -> str:
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Tool agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id, agent_id=agent.id, version=1, status="published",
                language="es-CO", timezone="America/Bogota",
                identity_json={"name": "Tool agent"}, instructions_json={"system_prompt": "Published"}, behavior_json={},
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"},
                    "tools": tools,
                },
            )
            db.add(version)
            db.flush()
            agent.status = "active"
            agent.published_version_id = version.id
            db.commit()
            session = VoiceSessionService(db).create(
                tenant_id, agent.id, channel="internal_test", direction="internal",
                lead_id=lead_id, contact_id=contact_id, caller_phone=caller_phone,
            )
            session.livekit_room_name = f"sg-vs-{session.id}"
            session.status = "dispatched"
            db.commit()
            return session.id

    def _invoke(self, session_id: str, tool_key: str, arguments: dict | None = None):
        with patch.object(settings, "VOICE_RUNTIME_SERVICE_SECRET", "x" * 32):
            token = create_runtime_token()
            return self.client.post(
                f"/api/v1/internal/voice-runtime/sessions/{session_id}/tools/{tool_key}/invoke",
                headers={"Authorization": f"Bearer {token}"},
                json={"arguments": arguments or {}},
            )

    def _configure_whatsapp(self, tenant_id: str) -> None:
        from app.models.integrations import TenantWhatsAppConfig
        from app.services.secret_manager_service import SecretManager

        with SessionLocal() as db:
            db.add(TenantWhatsAppConfig(
                tenant_id=tenant_id, provider="whatsapp_cloud", status="active",
                phone_number_id="phone-1", display_phone_number="+573000000000",
                default_language="es",
                access_token_encrypted=SecretManager().encrypt_secret("EA_test_token_1234567890"),
            ))
            db.commit()

    def test_requires_valid_runtime_authentication(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        response = self.client.post(
            f"/api/v1/internal/voice-runtime/sessions/{session_id}/tools/calendar.check_availability/invoke",
            json={"arguments": {"date": "mañana"}},
        )
        self.assertEqual(response.status_code, 401)

    def test_rejects_tool_not_bound_to_this_session(self) -> None:
        session_id = self._session_with_tools([])
        response = self._invoke(session_id, "calendar.check_availability", {"date": "mañana"})
        self.assertEqual(response.status_code, 404)
        self.assertIn("tool_not_found", response.text)

    def test_rejects_disabled_binding(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": False, "config": {}}])
        response = self._invoke(session_id, "calendar.check_availability", {"date": "mañana"})
        self.assertEqual(response.status_code, 404)

    def test_rejects_a_key_not_in_the_handler_allowlist_even_if_the_registry_says_available(self) -> None:
        # Defense in depth: this shape could only happen if the Registry and
        # the handler allowlist ever drifted apart -- proves the dispatcher
        # never falls back to executing an unrecognized key just because
        # the (mocked) Registry vouches for it.
        session_id = self._session_with_tools([{"key": "totally.new_tool", "enabled": True, "config": {}}])
        with patch("app.services.tool_dispatch_service.get_tool") as mocked:
            from app.domain.tool_registry import ToolDefinition

            mocked.return_value = ToolDefinition(
                key="totally.new_tool", name="X", description="X", status="available",
                input_schema={"type": "object", "properties": {}}, required_integration=None,
            )
            response = self._invoke(session_id, "totally.new_tool", {})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_not_available", response.text)

    def test_rejects_missing_required_argument(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "calendar.check_availability", {})
        self.assertEqual(response.status_code, 422)
        self.assertIn("tool_argument_invalid", response.text)

    def test_rejects_unknown_argument(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "calendar.check_availability", {"date": "mañana", "extra": "x"})
        self.assertEqual(response.status_code, 422)

    def test_rejects_wrong_argument_type(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "calendar.check_availability", {"date": 123})
        self.assertEqual(response.status_code, 422)

    def test_whatsapp_tool_succeeds_when_integration_is_configured(self) -> None:
        self._configure_whatsapp(self.tenant.id)
        session_id = self._session_with_tools([{"key": "whatsapp.send_message", "enabled": True, "config": {}}])
        with patch(
            "app.services.whatsapp_message_service.WhatsAppMessageService.send_template_notification"
        ) as mocked:
            from app.services.whatsapp_message_service import WhatsAppSendResult

            mocked.return_value = WhatsAppSendResult(status="sent", provider_message_id="wamid.123")
            response = self._invoke(session_id, "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "booking_confirmation"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"], {"status": "sent", "provider_message_id": "wamid.123"})

    def test_whatsapp_tool_fails_when_integration_is_not_configured(self) -> None:
        session_id = self._session_with_tools([{"key": "whatsapp.send_message", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "booking_confirmation"})
        self.assertEqual(response.status_code, 502)
        self.assertIn("tool_execution_failed", response.text)

    def test_rejects_terminal_session(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.check_availability", "enabled": True, "config": {}}])
        with SessionLocal() as db:
            VoiceSessionService(db).get(session_id).status = "ended"
            db.commit()
        response = self._invoke(session_id, "calendar.check_availability", {"date": "mañana"})
        self.assertEqual(response.status_code, 409)

    def test_result_never_contains_the_tools_binding_config(self) -> None:
        self._configure_whatsapp(self.tenant.id)
        session_id = self._session_with_tools([
            {"key": "whatsapp.send_message", "enabled": True, "config": {"internal_note": "should-not-leak"}}
        ])
        with patch(
            "app.services.whatsapp_message_service.WhatsAppMessageService.send_template_notification"
        ) as mocked:
            from app.services.whatsapp_message_service import WhatsAppSendResult

            mocked.return_value = WhatsAppSendResult(status="sent", provider_message_id="wamid.123")
            response = self._invoke(session_id, "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "booking_confirmation"})
        self.assertNotIn("should-not-leak", response.text)

    def test_tool_execution_uses_the_sessions_own_tenant_not_any_other(self) -> None:
        # The internal runtime channel authenticates as "voice-runtime", not
        # as a tenant user -- tenant isolation here means session_id alone
        # determines which tenant's integration config is resolved. Proven
        # by configuring WhatsApp only for tenant A and invoking through a
        # session that belongs to tenant B: it must fail exactly as it
        # would for any tenant with no WhatsApp integration, never succeed
        # by picking up tenant A's config.
        self._configure_whatsapp(self.tenant.id)
        other_tenant, _ = self._seed_tenant_user(slug="tenant-tools-c", email="tools-c@example.com")
        session_id = self._session_with_tools(
            [{"key": "whatsapp.send_message", "enabled": True, "config": {}}], tenant_id=other_tenant.id
        )
        response = self._invoke(session_id, "whatsapp.send_message", {"to_phone": "+573000000001", "template_key": "booking_confirmation"})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertIn("tool_execution_failed", response.text)

    # -- calendar.create_booking / crm.create_lead (Session Context V1) --

    def _seed_contact_and_lead(self, tenant_id: str, *, email: str = "carlos@example.com") -> tuple[str, str]:
        with SessionLocal() as db:
            stage = CrmPipelineStage(tenant_id=tenant_id, key="qualified", name="Qualified", position=1, is_default=True)
            contact = CrmContact(tenant_id=tenant_id, name="Carlos Pérez", phone="3001112233", phone_normalized="+573001112233", email=email)
            db.add_all([stage, contact])
            db.commit()
            db.refresh(stage)
            db.refresh(contact)
            lead = CrmLead(tenant_id=tenant_id, contact_id=contact.id, current_stage_id=stage.id, status="open")
            db.add(lead)
            db.commit()
            db.refresh(lead)
            return contact.id, lead.id

    def test_create_booking_tool_is_not_bound_to_llm_supplied_lead_id(self) -> None:
        # The LLM-visible input_schema for calendar.create_booking has no
        # lead_id/contact_id property at all -- passing one is simply an
        # unknown argument, proving the schema itself can't be used to
        # smuggle an identity override.
        _, lead_id = self._seed_contact_and_lead(self.tenant.id)
        session_id = self._session_with_tools(
            [{"key": "calendar.create_booking", "enabled": True, "config": {}}], lead_id=lead_id
        )
        response = self._invoke(session_id, "calendar.create_booking", {"start": "2026-09-15T15:00:00-05:00", "lead_id": "attacker-supplied-lead"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_argument_invalid", response.text)

    def test_create_booking_fails_closed_without_a_resolved_lead(self) -> None:
        session_id = self._session_with_tools([{"key": "calendar.create_booking", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "calendar.create_booking", {"start": "2026-09-15T15:00:00-05:00"})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertIn("lead_context_required", response.text)

    def test_create_booking_uses_session_lead_and_contact_never_llm_supplied(self) -> None:
        contact_id, lead_id = self._seed_contact_and_lead(self.tenant.id)
        session_id = self._session_with_tools(
            [{"key": "calendar.create_booking", "enabled": True, "config": {}}], lead_id=lead_id
        )
        with patch("app.services.booking_service.BookingService.create_lead_booking") as mocked:
            from app.models.crm import CrmBooking
            from datetime import datetime, timezone

            mocked.return_value = CrmBooking(
                id="booking-1", tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
                provider="calcom", title="x", status="confirmed",
                start_at=datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc),
                end_at=datetime(2026, 9, 15, 20, 30, tzinfo=timezone.utc),
                timezone="America/Bogota", duration_minutes=30,
                attendee_name="Carlos Pérez", attendee_email="carlos@example.com",
            )
            response = self._invoke(session_id, "calendar.create_booking", {"start": "2026-09-15T15:00:00-05:00"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(mocked.call_args.kwargs["lead_id"], lead_id)
        self.assertEqual(mocked.call_args.kwargs["body"].attendee_email, "carlos@example.com")

    def test_create_lead_tool_ignores_llm_supplied_phone_argument(self) -> None:
        # phone is not even in the LLM-visible input_schema -- passing one
        # is an unknown argument, same defense as the lead_id test above.
        session_id = self._session_with_tools(
            [{"key": "crm.create_lead", "enabled": True, "config": {}}], caller_phone="+573001112233"
        )
        response = self._invoke(session_id, "crm.create_lead", {"name": "Carlos", "phone": "+573009998877"})
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("tool_argument_invalid", response.text)

    def test_create_lead_fails_closed_without_a_known_caller_phone(self) -> None:
        session_id = self._session_with_tools([{"key": "crm.create_lead", "enabled": True, "config": {}}])
        response = self._invoke(session_id, "crm.create_lead", {"name": "Carlos"})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertIn("caller_phone_required", response.text)

    def test_create_lead_uses_session_caller_phone_and_creates_a_real_lead(self) -> None:
        session_id = self._session_with_tools(
            [{"key": "crm.create_lead", "enabled": True, "config": {}}], caller_phone="+573005556677"
        )
        response = self._invoke(session_id, "crm.create_lead", {"name": "Nueva Persona"})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertIn("lead_id", result)
        with SessionLocal() as db:
            contact = db.get(CrmContact, result["contact_id"])
            self.assertEqual(contact.phone_normalized, "+573005556677")
            self.assertEqual(contact.name, "Nueva Persona")


if __name__ == "__main__":
    unittest.main()
