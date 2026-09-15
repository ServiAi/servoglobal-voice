from __future__ import annotations

from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import patch

from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.models.agents import TenantAgent
from app.models.analytics import Agent, Call
from app.models.crm import CrmActivity, CrmLead, CrmVoiceCall
from app.models.voice_sessions import VoiceSession, VoiceSessionEvent
from app.schemas.crm import ActivitySchema
from app.services.voice_call_projection_service import VoiceCallProjectionService
from scripts.backfill_voice_session_calls import run as backfill


START = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


class VoiceCallProjectionTests(Integration2ATestCase):
    def _session(self, *, channel: str, direction: str, lead_id: str | None = None,
                 contact_id: str | None = None, crm_call: CrmVoiceCall | None = None) -> str:
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=self.tenant.id, name="Agente de prueba", status="active")
            db.add(agent)
            db.flush()
            if crm_call:
                db.add(crm_call)
                db.flush()
            context = {"schema_version": "1"}
            if contact_id:
                context["contact"] = {"id": contact_id}
            if lead_id:
                context["lead"] = {"id": lead_id}
            session = VoiceSession(
                tenant_id=self.tenant.id, agent_id=agent.id, provider="ultravox",
                channel=channel, direction=direction, status="ended",
                requested_at=START, started_at=START,
                connected_at=START + timedelta(seconds=10) if channel == "webrtc" else None,
                ended_at=START + timedelta(seconds=70),
                crm_voice_call_id=crm_call.id if crm_call else None,
                session_context_json=context,
            )
            db.add(session)
            db.commit()
            return session.id

    def _event(self, session_id: str, event_id: str, event_type: str, seconds: int,
               *, sequence: int | None = None, payload: dict | None = None) -> None:
        with SessionLocal() as db:
            db.add(VoiceSessionEvent(
                event_id=event_id, tenant_id=self.tenant.id, voice_session_id=session_id,
                event_type=event_type, source="livekit", sequence=sequence,
                occurred_at=START + timedelta(seconds=seconds), payload_json=payload or {},
            ))
            db.commit()

    def test_webrtc_without_crm_is_one_global_call_with_transcript_and_duration(self) -> None:
        session_id = self._session(channel="webrtc", direction="internal")
        with SessionLocal() as db:
            session = db.get(VoiceSession, session_id)
            session.status = "starting"
            db.commit()
            self.assertIsNone(VoiceCallProjectionService(db).project_session(session_id))
            session.status = "ended"
            db.commit()
        self._event(session_id, "assistant-1", "voice.transcript.final", 20,
                    sequence=2, payload={"speaker": "assistant", "text": "Hola"})
        self._event(session_id, "user-1", "voice.transcript.final", 12,
                    sequence=1, payload={"speaker": "user", "text": "Buenos días"})
        self._event(session_id, "connected-1", "voice.session.connected", 10)
        self._event(session_id, "ended-1", "voice.session.ended", 70)
        with SessionLocal() as db:
            service = VoiceCallProjectionService(db)
            first = service.project_session(session_id)
            second = service.reconcile_session(session_id)
            self.assertEqual(first.id, second.id)
            self.assertEqual(first.external_call_id, f"voice-session:{session_id}")
            self.assertEqual(first.external_provider, "ultravox")
            self.assertEqual((first.channel, first.direction), ("webrtc", "internal"))
            self.assertEqual(first.normalized_status, "answered")
            self.assertEqual(first.duration_seconds, 60)
            self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Agent)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCall)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmActivity)), 0)
            turns = list(db.scalars(select(VoiceSessionEvent).where(
                VoiceSessionEvent.voice_session_id == session_id,
                VoiceSessionEvent.event_type == "voice.transcript.final",
            )).all())
            self.assertEqual(len(turns), 2)
        response = self.client.get("/api/v1/dashboard/recent-calls")
        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual((item["agent_name"], item["external_provider"], item["channel"],
                          item["direction"], item["duration_seconds"]),
                         ("Agente de prueba", "ultravox", "webrtc", "internal", 60))
        kpis = self.client.get("/api/v1/dashboard/kpis")
        self.assertEqual(kpis.status_code, 200)
        self.assertEqual((kpis.json()["calls_total"], kpis.json()["calls_answered"]), (1, 1))

    def test_sip_crm_projects_activity_conversation_and_dashboard(self) -> None:
        lead_id, contact_id = self.seed_lead()
        crm_call = CrmVoiceCall(
            tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
            provider="livekit_sip", direction="outbound", status="completed",
            started_at=START, answered_at=START + timedelta(seconds=10),
            ended_at=START + timedelta(seconds=70),
        )
        session_id = self._session(channel="sip", direction="outbound", lead_id=lead_id,
                                   contact_id=contact_id, crm_call=crm_call)
        self._event(session_id, "sip-assistant", "voice.transcript.final", 22,
                    sequence=2, payload={"speaker": "assistant", "text": "¿En qué puedo ayudar?"})
        self._event(session_id, "sip-user", "voice.transcript.final", 14,
                    sequence=1, payload={"speaker": "user", "text": "Quiero una cita"})
        with SessionLocal() as db:
            call = VoiceCallProjectionService(db).project_session(session_id)
            VoiceCallProjectionService(db).project_session(session_id)
            activity = db.scalar(select(CrmActivity).where(CrmActivity.call_id == call.id))
            self.assertIsNotNone(activity)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmActivity)), 1)
            self.assertEqual([turn["speaker"] for turn in activity.payload_json["transcript"]],
                             ["user", "assistant"])
            activity_schema = ActivitySchema.model_validate(activity)
            self.assertEqual(activity_schema.transcript[0].text, "Quiero una cita")
            self.assertEqual(activity_schema.duration_seconds, 60)
            self.assertEqual(db.get(CrmLead, lead_id).last_call_id, call.id)
            self.assertEqual(db.get(CrmVoiceCall, crm_call.id).duration_seconds, 60)
            self.assertEqual(call.external_provider, "ultravox")
        history = self.client.get(f"/api/v1/crm/leads/{lead_id}/calls")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["agent_name"], "Agente de prueba")
        conversations = self.client.get(f"/api/v1/crm/leads/{lead_id}")
        self.assertEqual(conversations.status_code, 200)
        self.assertEqual(conversations.json()["activities"][0]["transcript"][0]["speaker"], "user")
        self.assertEqual(conversations.json()["activities"][0]["duration_seconds"], 60)
        recent = self.client.get("/api/v1/dashboard/recent-calls")
        self.assertEqual(recent.json()["items"][0]["channel"], "sip")

    def test_webrtc_with_valid_crm_context_only_creates_activity(self) -> None:
        lead_id, contact_id = self.seed_lead()
        session_id = self._session(channel="webrtc", direction="internal",
                                   lead_id=lead_id)
        self._event(session_id, "context-user", "voice.transcript.final", 12,
                    payload={"speaker": "user", "text": "Hola"})
        with SessionLocal() as db:
            call = VoiceCallProjectionService(db).project_session(session_id)
            activity = db.scalar(select(CrmActivity))
            self.assertEqual((activity.call_id, activity.lead_id), (call.id, lead_id))
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCall)), 0)
            self.assertEqual(db.get(CrmLead, lead_id).last_call_id, call.id)
            session = db.get(VoiceSession, session_id)
            session.provider = "future-provider"
            db.commit()
            reprojected = VoiceCallProjectionService(db).reconcile_session(session_id)
            self.assertEqual(reprojected.id, call.id)
            self.assertEqual(reprojected.external_provider, "future-provider")
            self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 1)
            with self.assertRaises(ValueError):
                VoiceCallProjectionService(db).project_session(session_id, tenant_id="another-tenant")
        conversations = self.client.get(f"/api/v1/crm/leads/{lead_id}")
        self.assertEqual(conversations.json()["activities"][0]["channel"], "webrtc")

    def test_requested_sip_is_not_counted_before_dial(self) -> None:
        lead_id, contact_id = self.seed_lead()
        crm_call = CrmVoiceCall(
            tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
            provider="livekit_sip", direction="outbound", status="requested",
        )
        session_id = self._session(channel="sip", direction="outbound", lead_id=lead_id,
                                   contact_id=contact_id, crm_call=crm_call)
        with SessionLocal() as db:
            session = db.get(VoiceSession, session_id)
            session.status = "requested"
            session.ended_at = None
            db.commit()
            self.assertIsNone(VoiceCallProjectionService(db).project_session(session_id))
            self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmActivity)), 0)
            call = db.get(CrmVoiceCall, crm_call.id)
            call.started_at = START
            call.status = "dialing"
            db.commit()
            projected = VoiceCallProjectionService(db).project_session(session_id)
            self.assertEqual(projected.normalized_status, "in_progress")
            self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 1)

    def test_no_answer_has_zero_duration_and_repeatable_backfill(self) -> None:
        lead_id, contact_id = self.seed_lead()
        crm_call = CrmVoiceCall(
            tenant_id=self.tenant.id, lead_id=lead_id, contact_id=contact_id,
            provider="livekit_sip", direction="outbound", status="no_answer",
            started_at=START, ended_at=START + timedelta(seconds=20),
        )
        session_id = self._session(channel="sip", direction="outbound", lead_id=lead_id,
                                   contact_id=contact_id, crm_call=crm_call)
        with patch("scripts.backfill_voice_session_calls.SessionLocal", SessionLocal):
            with redirect_stdout(StringIO()) as preview:
                self.assertEqual(backfill(tenant_id=self.tenant.id, batch_size=1, apply=False), 0)
            self.assertIn("eligible=1", preview.getvalue())
            with SessionLocal() as db:
                self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 0)
            self.assertEqual(backfill(tenant_id=self.tenant.id, batch_size=1, apply=True), 0)
            self.assertEqual(backfill(tenant_id=self.tenant.id, batch_size=1, apply=True), 0)
        with SessionLocal() as db:
            call = db.scalar(select(Call))
            self.assertEqual((call.normalized_status, call.duration_seconds), ("unanswered", 0))
            self.assertEqual(db.scalar(select(func.count()).select_from(Call)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmActivity)), 1)
