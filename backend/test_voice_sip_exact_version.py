from __future__ import annotations

from datetime import UTC, datetime

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.crm.infrastructure.models import CrmVoiceCall
from app.modules.voice.domain.errors import VoiceSessionError
from app.modules.voice.infrastructure.models import VoiceSession
from app.modules.voice.public import VoiceTelephonyFacade


class SipExactVersionTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=self.tenant.id, name="SIP agent", status="draft")
            db.add(agent)
            db.flush()
            v1 = self._version(agent.id, 1, "published")
            db.add(v1)
            db.flush()
            agent.status, agent.published_version_id = "active", v1.id
            db.commit()
            self.agent_id, self.v1 = agent.id, v1.id

    def _version(self, agent_id: str, number: int, status: str) -> TenantAgentVersion:
        return TenantAgentVersion(
            tenant_id=self.tenant.id, agent_id=agent_id, version=number, status=status, language="es",
            timezone="America/Bogota", identity_json={"name": "SIP agent"}, instructions_json={"system_prompt": "x"},
            behavior_json={}, runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
            published_at=datetime.now(UTC),
        )

    def _publish_v2(self) -> str:
        with SessionLocal() as db:
            v2 = self._version(self.agent_id, 2, "published")
            db.add(v2)
            db.flush()
            db.get(TenantAgentVersion, self.v1).status = "superseded"
            db.get(TenantAgent, self.agent_id).published_version_id = v2.id
            db.commit()
            return v2.id

    def test_the_session_is_pinned_to_the_requested_version_not_the_published_one(self) -> None:
        v2 = self._publish_v2()
        with SessionLocal() as db:
            exact = VoiceTelephonyFacade(db).create_outbound_sip_session_from_agent_version(
                self.tenant.id, self.agent_id, self.v1, idempotency_key="k-exact",
                contact_id=None, lead_id=None, caller_phone="+573001112233", variables={"plan": "pro"},
            )
            current = VoiceTelephonyFacade(db).create_outbound_sip_session(
                self.tenant.id, self.agent_id, idempotency_key="k-current",
                contact_id=None, lead_id=None, caller_phone="+573001112233",
            )
            row = db.get(VoiceSession, exact.id)
            self.assertEqual((exact.agent_version_id, current.agent_version_id), (self.v1, v2))
            self.assertEqual((row.channel, row.direction, row.purpose), ("sip", "outbound", "production"))
            self.assertEqual(row.session_context_json["variables"], {"plan": "pro"})
            replay = VoiceTelephonyFacade(db).create_outbound_sip_session_from_agent_version(
                self.tenant.id, self.agent_id, self.v1, idempotency_key="k-exact",
                contact_id=None, lead_id=None, caller_phone="+573001112233",
            )
            self.assertEqual(replay.id, exact.id)

    def test_an_archived_agent_or_a_draft_version_cannot_be_placed(self) -> None:
        with SessionLocal() as db:
            draft = self._version(self.agent_id, 2, "draft")
            db.add(draft)
            db.commit()
            facade = VoiceTelephonyFacade(db)
            with self.assertRaises(VoiceSessionError):
                facade.create_outbound_sip_session_from_agent_version(
                    self.tenant.id, self.agent_id, draft.id, idempotency_key="k-draft",
                    contact_id=None, lead_id=None, caller_phone="+573001112233",
                )
            db.get(TenantAgent, self.agent_id).status = "archived"
            db.commit()
            with self.assertRaises(VoiceSessionError):
                facade.create_outbound_sip_session_from_agent_version(
                    self.tenant.id, self.agent_id, self.v1, idempotency_key="k-archived",
                    contact_id=None, lead_id=None, caller_phone="+573001112233",
                )

    def test_channel_count_excludes_the_session_of_the_call_being_placed(self) -> None:
        with SessionLocal() as db:
            facade = VoiceTelephonyFacade(db)
            session = facade.create_outbound_sip_session_from_agent_version(
                self.tenant.id, self.agent_id, self.v1, idempotency_key="k-count",
                contact_id=None, lead_id=None, caller_phone="+573001112233",
            )
            call = CrmVoiceCall(tenant_id=self.tenant.id, provider="livekit_sip", direction="outbound", status="starting")
            db.add(call)
            db.flush()
            facade.correlate_crm_call(session.id, self.tenant.id, call.id)
            db.get(VoiceSession, session.id).sip_route_id = "route-1"
            db.commit()
            self.assertEqual(facade.count_active_telephony_sessions(self.tenant.id, "route-1"), 1)
            self.assertEqual(
                facade.count_active_telephony_sessions(self.tenant.id, "route-1", exclude_crm_call_id=call.id), 0
            )


if __name__ == "__main__":
    import unittest

    unittest.main()
