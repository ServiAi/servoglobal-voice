from __future__ import annotations

import unittest

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.agents import TenantAgent, TenantAgentVersion
from app.services.voice_session_service import VoiceSessionError, VoiceSessionService


class VoiceSessionTests(Integration2ATestCase):
    def _published_agent(self, *, tenant_id: str | None = None, status: str = "active") -> str:
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id or self.tenant.id, name="Sandra", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=agent.tenant_id, agent_id=agent.id, version=1, status="published",
                language="es-CO", timezone="America/Bogota", identity_json={"name": "Sandra"},
                instructions_json={"system_prompt": "Published prompt", "greeting": "Hola"},
                behavior_json={}, runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"}},
            )
            db.add(version)
            db.flush()
            agent.published_version_id = version.id
            agent.status = status
            db.commit()
            return agent.id

    def test_create_pins_version_and_is_idempotent(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            first = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal", idempotency_key="same")
            version_id = first.agent_version_id
            second = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal", idempotency_key="same")
            self.assertEqual(first.id, second.id)
            self.assertEqual(second.agent_version_id, version_id)
            self.assertEqual(first.events[0].event_type, "voice.session.requested")

    def test_rejects_non_active_agent_and_cross_tenant_lookup(self) -> None:
        agent_id = self._published_agent(status="draft")
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            with self.assertRaises(VoiceSessionError):
                service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal")

    def test_lifecycle_rejects_invalid_transition(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            session = service.create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            with self.assertRaises(VoiceSessionError):
                service.transition(session, "connected")

    def test_agent_version_is_immutable(self) -> None:
        agent_id = self._published_agent()
        with SessionLocal() as db:
            session = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            session.agent_version_id = "another-version"
            with self.assertRaises(ValueError):
                db.commit()


if __name__ == "__main__":
    unittest.main()
