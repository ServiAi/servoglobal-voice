import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.crm import CrmVoiceCall
from app.models.integrations import TenantSipRoute
from app.models.voice_sessions import VoiceSession
from app.services.tool_dispatch_service import ToolDispatchService, ToolExecutionError
from app.services.voice_session_service import VoiceSessionService
from app.services.voice_session_sip_service import VoiceSessionSipService
from app.services.tenant_feature_service import TenantFeatureService, VOICE_RUNTIME_V2
from test_outbound_voice_call_service import FakeSip, ReadyBackend


class VoiceQaHarnessTests(Integration2ATestCase):
    def _agent(self, tenant_id: str | None = None, tools: list[dict] | None = None) -> str:
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="QA agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id,
                agent_id=agent.id,
                version=1,
                status="published",
                language="es-CO",
                timezone="America/Bogota",
                identity_json={"name": "QA agent"},
                instructions_json={"system_prompt": "Published"},
                behavior_json={},
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"},
                    "tools": tools or [],
                },
            )
            db.add(version)
            db.flush()
            agent.status = "active"
            agent.published_version_id = version.id
            db.commit()
            return agent.id

    def _session(self, tenant_id: str | None = None) -> str:
        tenant_id = tenant_id or self.tenant.id
        agent_id = self._agent(tenant_id)
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                tenant_id,
                agent_id,
                channel="webrtc",
                direction="internal",
                purpose="qa",
                caller_phone="+573001112233",
                variables={"campaign_label": "qa"},
            )
            return session.id

    def _route(self) -> None:
        response = self.client.post(
            "/api/v1/integrations/voice/config",
            json={
                "provider": "ultravox",
                "api_key": "tenant-ultravox-key",
                "status": "active",
                "sip_route": {
                    "status": "active",
                    "pbx_host": "pbx.example.com",
                    "pbx_port": 5060,
                    "sip_password": "test-sip-password",
                    "caller_id": "+573001112233",
                    "default_country": "CO",
                    "allowed_countries": ["CO"],
                    "max_concurrent_calls": 1,
                },
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            route = db.scalar(select(TenantSipRoute).where(TenantSipRoute.tenant_id == self.tenant.id))
            route.applied_revision = route.desired_revision
            route.provision_status = "active"
            route.livekit_outbound_trunk_id = "ST_qa"
            route.livekit_provision_status = "active"
            db.commit()

    def test_events_are_tenant_scoped_and_payloads_are_sanitized(self) -> None:
        session_id = self._session()
        with SessionLocal() as db:
            session = VoiceSessionService(db).get(session_id)
            service = VoiceSessionService(db)
            service.record_event(
                session,
                "voice.transcript.final",
                source="voice-runtime",
                payload={"speaker": "user", "text": "Hola", "authorization": "secret"},
            )
            service.record_event(
                session,
                "session.context.tool_used",
                source="control-plane",
                payload={
                    "tool_key": "calendar.create_booking",
                    "status": "error",
                    "duration_ms": 12,
                    "error_code": "lead_context_required",
                    "arguments": {"secret": True},
                },
            )

        response = self.client.get(f"/api/v1/voice/sessions/{session_id}/events")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["session"]["purpose"], "qa")
        self.assertEqual(body["context"]["caller_phone"], "***2233")
        self.assertEqual(body["context"]["variables"], {"campaign_label": "qa"})
        self.assertNotIn("authorization", str(body))
        self.assertNotIn("arguments", str(body))
        self.assertIn("lead_context_required", str(body))

        other_tenant, _ = self._seed_tenant_user(slug="qa-events-b", email="qa-events-b@example.com")
        other_session = self._session(other_tenant.id)
        self.assertEqual(
            self.client.get(f"/api/v1/voice/sessions/{other_session}/events").status_code,
            404,
        )

    def test_webrtc_qa_creation_resolves_existing_lead_and_variables(self) -> None:
        agent_id = self._agent()
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id, VOICE_RUNTIME_V2, True, {}, self.user.id
            )
        with patch(
            "app.api.endpoints.voice_runtime.VoiceRuntimeDispatcher.dispatch",
            new_callable=AsyncMock,
            side_effect=lambda session: session,
        ):
            response = self.client.post(
                "/api/v1/voice/sessions",
                json={
                    "agent_id": agent_id,
                    "channel": "webrtc",
                    "direction": "internal",
                    "purpose": "qa",
                    "lead_id": lead_id,
                    "variables": {"scenario": "existing_lead"},
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["purpose"], "qa")
        with SessionLocal() as db:
            session = db.get(VoiceSession, response.json()["id"])
            self.assertEqual(session.session_context_json["lead"]["id"], lead_id)
            self.assertEqual(session.session_context_json["contact"]["id"], contact_id)
            self.assertEqual(session.session_context_json["variables"], {"scenario": "existing_lead"})

    def test_webrtc_conversation_starts_without_preloaded_context(self) -> None:
        agent_id = self._agent()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id, VOICE_RUNTIME_V2, True, {}, self.user.id
            )
        with patch(
            "app.api.endpoints.voice_runtime.VoiceRuntimeDispatcher.dispatch",
            new_callable=AsyncMock,
            side_effect=lambda session: session,
        ):
            response = self.client.post(
                "/api/v1/voice/sessions",
                json={
                    "agent_id": agent_id,
                    "channel": "webrtc",
                    "direction": "internal",
                    "purpose": "qa",
                    "qa_context_mode": "conversation",
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        with SessionLocal() as db:
            context = db.get(VoiceSession, response.json()["id"]).session_context_json
            self.assertIsNone(context["caller"])
            self.assertIsNone(context["contact"])
            self.assertIsNone(context["lead"])
            self.assertEqual(context["variables"], {})

    def test_sip_conversation_uses_destination_as_transport_identity_only(self) -> None:
        agent_id = self._agent()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(
                self.tenant.id, VOICE_RUNTIME_V2, True, {}, self.user.id
            )
        with patch(
            "app.api.endpoints.voice_runtime.VoiceSessionSipService.dial",
            new_callable=AsyncMock,
            side_effect=lambda session, _to_phone: session,
        ):
            response = self.client.post(
                "/api/v1/voice/sessions",
                json={
                    "agent_id": agent_id,
                    "channel": "sip",
                    "direction": "outbound",
                    "purpose": "qa",
                    "qa_context_mode": "conversation",
                    "to_phone": "+573001234567",
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        with SessionLocal() as db:
            context = db.get(VoiceSession, response.json()["id"]).session_context_json
            self.assertEqual(context["caller"]["phone"], "+573001234567")
            self.assertIsNone(context["contact"])
            self.assertIsNone(context["lead"])
            self.assertEqual(context["variables"], {})

    def test_conversation_rejects_preloaded_business_context(self) -> None:
        agent_id = self._agent()
        invalid_fields = (
            {"lead_id": "lead-id"},
            {"contact_id": "contact-id"},
            {"variables": {"campaign": "qa"}},
            {"caller_phone": "+573001112233"},
        )
        for extra in invalid_fields:
            with self.subTest(extra=extra):
                response = self.client.post(
                    "/api/v1/voice/sessions",
                    json={
                        "agent_id": agent_id,
                        "channel": "webrtc",
                        "direction": "internal",
                        "purpose": "qa",
                        "qa_context_mode": "conversation",
                        **extra,
                    },
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertIn("qa_conversation_context_must_be_empty", response.text)

    def test_sip_conversation_create_lead_enriches_context_from_transport_caller(self) -> None:
        agent_id = self._agent(tools=[{"key": "crm.create_lead", "enabled": True}])
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id,
                agent_id,
                channel="sip",
                direction="outbound",
                purpose="qa",
                qa_context_mode="conversation",
                caller_phone="+573001234567",
            )
            result = ToolDispatchService(db).invoke(
                session.id, "crm.create_lead", {"name": "QA Conversacional", "email": "qa@example.com"}
            )
            db.refresh(session)
            self.assertEqual(session.session_context_json["caller"]["phone"], "+573001234567")
            self.assertEqual(session.session_context_json["contact"]["id"], result["contact_id"])
            self.assertEqual(session.session_context_json["lead"]["id"], result["lead_id"])

    def test_webrtc_conversation_create_lead_still_requires_trusted_caller(self) -> None:
        agent_id = self._agent(tools=[{"key": "crm.create_lead", "enabled": True}])
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id,
                agent_id,
                channel="webrtc",
                direction="internal",
                purpose="qa",
                qa_context_mode="conversation",
            )
            with self.assertRaisesRegex(ToolExecutionError, "caller_phone_required"):
                ToolDispatchService(db).invoke(session.id, "crm.create_lead", {"name": "QA"})

    def test_conversation_booking_still_requires_resolved_lead(self) -> None:
        agent_id = self._agent(tools=[{"key": "calendar.create_booking", "enabled": True}])
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id,
                agent_id,
                channel="sip",
                direction="outbound",
                purpose="qa",
                qa_context_mode="conversation",
                caller_phone="+573001234567",
            )
            with self.assertRaisesRegex(ToolExecutionError, "lead_context_required"):
                ToolDispatchService(db).invoke(
                    session.id,
                    "calendar.create_booking",
                    {"start": "2026-09-24T10:00:00-05:00"},
                )

    def test_sip_qa_dials_without_creating_crm_voice_call(self) -> None:
        self._route()
        agent_id = self._agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(
                self.tenant.id,
                agent_id,
                channel="sip",
                direction="outbound",
                purpose="qa",
            )
            result = asyncio.run(
                VoiceSessionSipService(
                    db,
                    sip_service=FakeSip([]),
                    runtime_backend=ReadyBackend([]),
                ).dial(session, "+573001112244")
            )
            self.assertEqual(result.purpose, "qa")
            self.assertEqual(result.sip_call_id, "SC_1")
            self.assertIsNone(result.crm_voice_call_id)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCall)), 0)


if __name__ == "__main__":
    unittest.main()
