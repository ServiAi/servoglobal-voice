from __future__ import annotations

import unittest
from datetime import UTC, datetime
from sqlalchemy import select
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.modules.analytics.infrastructure.models import Agent
from app.modules.crm.infrastructure.models import CrmVoiceCall, CrmVoiceCallEvent, CrmActivity
from app.models.integrations import TenantVoiceProviderConfig, TenantVoiceAgentConfig
from app.modules.integrations.infrastructure.models import TenantIntegrationEvent
from app.modules.telephony.application.route_service import SipRouteService


class CrmVoiceActionTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        self.provider = "ultravox"

    def configure_voice(self, *, provisioned=True):
        response = self.client.post(
            "/api/v1/integrations/voice/config",
            json={
                "provider": self.provider,
                "display_name": "My Ultravox",
                "api_key": "uvx_api_secret_token_12345",
                "webhook_secret": "wh_secret_123",
                "default_from_number": "+573001112233",
                "default_language": "es",
                "default_timezone": "America/Bogota",
                "status": "active",
                "sip_route": {
                    "status": "active",
                    "pbx_host": "pbx.example.com",
                    "pbx_port": 5060,
                    "sip_username": "tenant-a",
                    "sip_password": "test-sip-password",
                    "caller_id": "+573001112233",
                    "default_country": "CO",
                    "allowed_countries": ["CO"],
                    "max_concurrent_calls": 1,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        if provisioned:
            with SessionLocal() as db:
                route = SipRouteService(db).get_route(self.tenant.id)
                self.assertIsNotNone(route)
                route.applied_revision = route.desired_revision
                route.provision_status = "active"
                db.commit()
        return response.json()

    def test_voice_config_lifecycle(self):
        # 1. Config provider
        data = self.configure_voice()
        self.assertEqual(data["provider"], "ultravox")
        self.assertEqual(data["display_name"], "My Ultravox")
        self.assertTrue(data["has_secret"])
        self.assertTrue(data["has_webhook_secret"])
        self.assertEqual(data["status"], "active")
        self.assertEqual(
            data["sip_route"]["sip_username"],
            f"route-{data['sip_route']['id'].replace('-', '')}",
        )
        self.assertTrue(data["sip_route"]["has_sip_password"])
        self.assertNotIn("sip_password", data["sip_route"])

        # 2. Get config
        response = self.client.get("/api/v1/integrations/voice/config")
        self.assertEqual(response.status_code, 200)
        get_data = response.json()
        self.assertEqual(get_data["display_name"], "My Ultravox")
        self.assertTrue(get_data["has_secret"])
        self.assertNotIn("sip_password", get_data["sip_route"])

    def test_voice_agent_config(self):
        self.configure_voice()

        # Create agent config
        response = self.client.post(
            "/api/v1/integrations/voice/agents",
            json={
                "provider_agent_id": "wk-agent-123",
                "display_name": "Agente Comercial",
                "description": "Atiende llamadas de ventas",
                "purpose": "Ventas y Generación de Leads",
                "default_language": "es",
                "default_timezone": "America/Bogota",
                "default_voice": "standard-female",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 200)
        agent_data = response.json()
        self.assertEqual(agent_data["provider_agent_id"], "wk-agent-123")
        self.assertEqual(agent_data["display_name"], "Agente Comercial")

        # List agents
        response = self.client.get("/api/v1/integrations/voice/agents")
        self.assertEqual(response.status_code, 200)
        agents_list = response.json()
        self.assertEqual(len(agents_list), 1)
        self.assertEqual(agents_list[0]["id"], agent_data["id"])

        # Creating the agent config mirrors it into the analytics `agents`
        # table so calls resolve to a name instead of showing "Unassigned".
        with SessionLocal() as db:
            analytics_agent = db.scalar(
                select(Agent).where(
                    Agent.tenant_id == self.tenant.id,
                    Agent.external_provider == "ultravox",
                    Agent.external_agent_id == "wk-agent-123",
                )
            )
            self.assertIsNotNone(analytics_agent)
            self.assertEqual(analytics_agent.name, "Agente Comercial")
            self.assertEqual(analytics_agent.status, "active")

        # Updating the agent config keeps the mirror in sync.
        update_response = self.client.put(
            f"/api/v1/integrations/voice/agents/{agent_data['id']}",
            json={
                "provider_agent_id": "wk-agent-123",
                "display_name": "Agente Comercial Renombrado",
                "purpose": "Ventas y Generación de Leads",
                "default_language": "es",
                "default_timezone": "America/Bogota",
                "status": "inactive",
            },
        )
        self.assertEqual(update_response.status_code, 200)
        with SessionLocal() as db:
            analytics_agent = db.scalar(
                select(Agent).where(
                    Agent.tenant_id == self.tenant.id,
                    Agent.external_provider == "ultravox",
                    Agent.external_agent_id == "wk-agent-123",
                )
            )
            self.assertIsNotNone(analytics_agent)
            self.assertEqual(analytics_agent.name, "Agente Comercial Renombrado")
            self.assertEqual(analytics_agent.status, "inactive")

    def _agent_and_lead(self):
        self.configure_voice()
        agent = self.client.post(
            "/api/v1/integrations/voice/agents",
            json={
                "provider_agent_id": "wk-agent-kill",
                "display_name": "Agente Ventas",
                "purpose": "Ventas y Generación de Leads",
                "status": "active",
            },
        ).json()
        lead_id, _ = self.seed_lead()
        return agent["id"], lead_id

    def test_outbound_call_is_refused_without_side_effects_when_a_canonical_flag_is_off(self):
        from app.modules.identity.application.feature_service import (
            LIVEKIT_SIP_OUTBOUND_V2,
            VOICE_RUNTIME_V2,
            TenantFeatureService,
        )
        from app.modules.voice.infrastructure.models import VoiceSession

        agent_id, lead_id = self._agent_and_lead()
        for enabled in ((), (VOICE_RUNTIME_V2,), (LIVEKIT_SIP_OUTBOUND_V2,)):
            with self.subTest(enabled=enabled):
                with SessionLocal() as db:
                    features = TenantFeatureService(db)
                    for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                        features.set_feature(self.tenant.id, key, key in enabled, {}, self.user.id)
                response = self.client.post(
                    f"/api/v1/crm/leads/{lead_id}/actions/call", json={"agent_config_id": agent_id}
                )
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()["detail"], "Voice calling is currently unavailable.")
                with SessionLocal() as db:  # the kill switch fires before anything is persisted
                    self.assertEqual(db.query(CrmVoiceCall).count(), 0)
                    self.assertEqual(db.query(VoiceSession).count(), 0)

    def test_webhook_updates_status_correctly(self):
        # Seed lead and create a mock voice call
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            call = CrmVoiceCall(
                tenant_id=self.tenant.id,
                lead_id=lead_id,
                contact_id=contact_id,
                provider="ultravox",
                provider_call_id="uvx-call-999",
                provider_session_id="uvx-session-999",
                direction="outbound",
                status="queued",
                to_phone="+573001112233",
            )
            db.add(call)
            db.commit()
            voice_call_id = call.id

        # Send webhook event
        payload = {
            "event": "call.ended",
            "call": {
                "id": "uvx-call-999",
                "sessionId": "uvx-session-999",
                "status": "completed",
                "endReason": "completed",
                "duration": "45.5s",
                "recordingUrl": "https://ultravox.ai/recordings/999.mp3",
                "summary": "El cliente esta interesado en la propiedad",
                "metadata": {
                    "voice_call_id": voice_call_id,
                    "tenant_id": self.tenant.id,
                }
            }
        }

        # Post to webhook
        response = self.client.post(
            "/api/v1/voice/webhook/ultravox",
            json=payload,
            headers={
                "x-ultravox-webhook-timestamp": "2026-07-04T12:00:00Z",
                "x-ultravox-webhook-signature": "dummy-signature",
            }
        )
        self.assertEqual(response.status_code, 200)

        # Verify DB voice call status is updated
        with SessionLocal() as db:
            updated_call = db.get(CrmVoiceCall, voice_call_id)
            self.assertEqual(updated_call.status, "completed")
            self.assertEqual(updated_call.duration_seconds, 45)
            self.assertEqual(updated_call.recording_url, "https://ultravox.ai/recordings/999.mp3")
            self.assertEqual(updated_call.summary, "El cliente esta interesado en la propiedad")

            # Check call events
            event = db.scalar(select(CrmVoiceCallEvent).where(
                CrmVoiceCallEvent.voice_call_id == voice_call_id,
                CrmVoiceCallEvent.event_type == "call.ended"
            ))
            self.assertIsNotNone(event)

            # Check CRM Activity was logged for call completion
            activity = db.scalar(select(CrmActivity).where(
                CrmActivity.lead_id == lead_id,
                CrmActivity.activity_type == "voice_call_completed"
            ))
            self.assertIsNotNone(activity)
            self.assertIn("El cliente esta interesado", activity.description)

    def test_late_started_webhook_does_not_reopen_completed_call(self):
        with SessionLocal() as db:
            call = CrmVoiceCall(
                tenant_id=self.tenant.id,
                provider="ultravox",
                provider_call_id="uvx-terminal-call",
                direction="outbound",
                status="completed",
                ended_at=datetime.now(UTC),
            )
            db.add(call)
            db.commit()
            voice_call_id = call.id

        response = self.client.post(
            "/api/v1/voice/webhook/ultravox",
            json={
                "event": "call.started",
                "call": {
                    "id": "uvx-terminal-call",
                    "status": "queued",
                    "metadata": {"voice_call_id": voice_call_id},
                },
            },
            headers={
                "x-ultravox-webhook-timestamp": "2026-07-04T12:00:00Z",
                "x-ultravox-webhook-signature": "dummy-signature",
            },
        )
        self.assertEqual(response.status_code, 200)

        with SessionLocal() as db:
            self.assertEqual(db.get(CrmVoiceCall, voice_call_id).status, "completed")

    def test_voice_cross_tenant_isolation(self):
        # Create tenant B
        other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")
        other_lead_id, _ = self.seed_lead(tenant_id=other_tenant.id)

        self.configure_voice()
        from app.modules.identity.application.feature_service import (
            LIVEKIT_SIP_OUTBOUND_V2,
            VOICE_RUNTIME_V2,
            TenantFeatureService,
        )

        with SessionLocal() as db:  # calling must be enabled to reach the tenant check
            for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                TenantFeatureService(db).set_feature(self.tenant.id, key, True, {}, self.user.id)

        # Try to call lead belonging to other tenant
        response = self.client.post(
            f"/api/v1/crm/leads/{other_lead_id}/actions/call",
            json={"to_phone": "+573001112233"},
        )
        if response.status_code != 422:
            print("CROSS TENANT CALL RESPONSE:", response.status_code, response.text)
        self.assertEqual(response.status_code, 422)
