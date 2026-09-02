from __future__ import annotations

from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.crm import CrmActivity, CrmLead
from app.models.integrations import TenantChatwootConfig, TenantVoiceAgentConfig


class VoiceHandoffToolsTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        self._old_voice_secret = settings.VOICE_TOOL_SHARED_SECRET
        settings.VOICE_TOOL_SHARED_SECRET = "voice-secret-test"
        self.voice_headers = {"X-Voice-Tool-Secret": "voice-secret-test"}

    def tearDown(self):
        settings.VOICE_TOOL_SHARED_SECRET = self._old_voice_secret
        super().tearDown()

    def _configure_chatwoot(self):
        with SessionLocal() as db:
            db.add(
                TenantChatwootConfig(
                    tenant_id=self.tenant.id,
                    provider="chatwoot",
                    mode="external",
                    status="active",
                    base_url="https://crm.serviglobal-ia.com",
                    account_id=17,
                    api_token_encrypted=self._encrypt("cw_secret_token_1234567890"),
                    webhook_key="wk_handoff_test",
                )
            )
            db.commit()

    def _encrypt(self, value: str) -> str:
        from app.services.secret_manager_service import SecretManager

        return SecretManager().encrypt_secret(value)

    def _seed_agent(self, *, handoff_triggers: list[str], inbox_id: int | None = 5, team_id: int | None = 9):
        with SessionLocal() as db:
            db.add(
                TenantVoiceAgentConfig(
                    tenant_id=self.tenant.id,
                    provider="ultravox",
                    provider_agent_id="agent-voice-1",
                    display_name="Sandra Ventas",
                    purpose="Ventas y Generación de Leads",
                    handoff_enabled=True,
                    handoff_chatwoot_inbox_id=inbox_id,
                    handoff_chatwoot_team_id=team_id,
                    handoff_triggers=handoff_triggers,
                    handoff_lead_score_threshold=80,
                )
            )
            db.commit()

    def test_handoff_tool_ignored_when_agent_not_configured(self):
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        self._configure_chatwoot()
        with SessionLocal() as db:
            db.add(
                TenantVoiceAgentConfig(
                    tenant_id=self.tenant.id,
                    provider="ultravox",
                    provider_agent_id="agent-voice-1",
                    display_name="Sandra Ventas",
                    handoff_enabled=False,
                )
            )
            db.commit()

        response = self.client.post(
            "/api/v1/voice/tools/request-human-handoff",
            headers=self.voice_headers,
            json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")

    def test_handoff_tool_creates_chatwoot_conversation_and_activity(self):
        lead_id, contact_id = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        self._configure_chatwoot()
        self._seed_agent(handoff_triggers=["customer_request"])

        with (
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_contact", new_callable=AsyncMock) as get_contact,
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_conversation", new_callable=AsyncMock) as get_conv,
            patch("app.services.voice_handoff_service.ChatwootClient.assign_team", new_callable=AsyncMock) as assign_team,
            patch("app.services.voice_handoff_service.ChatwootClient.send_message", new_callable=AsyncMock) as send_message,
        ):
            get_contact.return_value = 555
            get_conv.return_value = 321
            assign_team.return_value = True
            send_message.return_value = True

            response = self.client.post(
                "/api/v1/voice/tools/request-human-handoff",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1", "reason": "customer asked"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        get_conv.assert_awaited_once_with(555, inbox_id=5)
        assign_team.assert_awaited_once_with(321, 9)
        send_message.assert_awaited_once()

        with SessionLocal() as db:
            activity = db.scalar(
                select(CrmActivity).where(
                    CrmActivity.lead_id == lead_id,
                    CrmActivity.activity_type == "chatwoot_handoff",
                )
            )
        self.assertIsNotNone(activity)
        self.assertEqual(activity.deduplication_key, f"handoff:customer_request:{lead_id}")

    def test_handoff_tool_does_not_duplicate_on_repeated_call(self):
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        self._configure_chatwoot()
        self._seed_agent(handoff_triggers=["customer_request"])

        with (
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_contact", new_callable=AsyncMock, return_value=555),
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_conversation", new_callable=AsyncMock, return_value=321),
            patch("app.services.voice_handoff_service.ChatwootClient.assign_team", new_callable=AsyncMock, return_value=True),
            patch("app.services.voice_handoff_service.ChatwootClient.send_message", new_callable=AsyncMock, return_value=True) as send_message,
        ):
            first = self.client.post(
                "/api/v1/voice/tools/request-human-handoff",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1"},
            )
            second = self.client.post(
                "/api/v1/voice/tools/request-human-handoff",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1"},
            )

        self.assertEqual(first.json()["status"], "ok")
        self.assertEqual(second.json(), {"status": "ignored", "reason": "already_handed_off"})
        send_message.assert_awaited_once()
        with SessionLocal() as db:
            activities = list(
                db.scalars(select(CrmActivity).where(CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "chatwoot_handoff"))
            )
        self.assertEqual(len(activities), 1)

    def test_lead_score_handoff_triggers_from_booking_availability_tool(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        self._configure_chatwoot()
        self._seed_agent(handoff_triggers=["lead_score"])
        with SessionLocal() as db:
            lead = db.get(CrmLead, lead_id)
            lead.lead_score = 92
            db.commit()

        with (
            patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots,
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_contact", new_callable=AsyncMock, return_value=555),
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_conversation", new_callable=AsyncMock, return_value=321),
            patch("app.services.voice_handoff_service.ChatwootClient.assign_team", new_callable=AsyncMock, return_value=True),
            patch("app.services.voice_handoff_service.ChatwootClient.send_message", new_callable=AsyncMock, return_value=True) as send_message,
        ):
            get_slots.return_value = {"date": "2026-07-02", "jornada": "all", "available_slots": [], "summary": ""}
            response = self.client.post(
                "/api/v1/voice/tools/availability",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1", "date": "2026-07-02"},
            )

        self.assertEqual(response.status_code, 200)
        send_message.assert_awaited_once()
        with SessionLocal() as db:
            activity = db.scalar(
                select(CrmActivity).where(CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "chatwoot_handoff")
            )
        self.assertIsNotNone(activity)
        self.assertIn("score 92", activity.description)

    def test_lead_score_below_threshold_does_not_trigger_handoff(self):
        self.configure_calcom()
        lead_id, _ = self.seed_lead(context_id="ctx-voice")
        self.seed_call_context(context_id="ctx-voice")
        self._configure_chatwoot()
        self._seed_agent(handoff_triggers=["lead_score"])
        with SessionLocal() as db:
            lead = db.get(CrmLead, lead_id)
            lead.lead_score = 40
            db.commit()

        with (
            patch("app.services.booking_service.CalComClient.get_available_slots") as get_slots,
            patch("app.services.voice_handoff_service.ChatwootClient.get_or_create_contact", new_callable=AsyncMock) as get_contact,
        ):
            get_slots.return_value = {"date": "2026-07-02", "jornada": "all", "available_slots": [], "summary": ""}
            response = self.client.post(
                "/api/v1/voice/tools/availability",
                headers=self.voice_headers,
                json={"call_context_id": "ctx-voice", "agent_id": "agent-voice-1", "date": "2026-07-02"},
            )

        self.assertEqual(response.status_code, 200)
        get_contact.assert_not_awaited()
        with SessionLocal() as db:
            activity = db.scalar(
                select(CrmActivity).where(CrmActivity.lead_id == lead_id, CrmActivity.activity_type == "chatwoot_handoff")
            )
        self.assertIsNone(activity)


if __name__ == "__main__":
    import unittest

    unittest.main()
