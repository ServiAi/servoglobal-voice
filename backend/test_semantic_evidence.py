from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Tenant
from app.modules.agents.domain.views import AgentEvaluationSnapshotUnavailableError
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.agents.public import AgentsFacade
from app.modules.evaluations.domain.semantic_evidence import (
    redact_text,
    SemanticEvidenceUnavailableError,
    build_semantic_evidence,
)
from app.modules.voice.application.facade import VoiceSessionOperations
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.domain.errors import VoiceConversationEvidenceNotReadyError, VoiceSessionNotFoundError
from app.modules.voice.domain.views import TranscriptCompleteness
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent


class SemanticEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant_id = str(uuid4())
        self.agent_id = str(uuid4())
        self.version3_id = str(uuid4())
        self.version7_id = str(uuid4())
        self.session_id = str(uuid4())
        self.db.add(Tenant(id=self.tenant_id, name="Evidence test", slug=f"ev-{self.tenant_id[:8]}"))
        agent = TenantAgent(
            id=self.agent_id,
            tenant_id=self.tenant_id,
            name="Sales agent",
            status="active",
            published_version_id=self.version7_id,
        )
        self.db.add(agent)
        self.db.flush()
        self.db.add_all(
            [
                self._version(self.version3_id, 3, "superseded"),
                self._version(self.version7_id, 7, "published"),
            ]
        )
        self.db.flush()
        self.db.add(
            VoiceSession(
                id=self.session_id,
                tenant_id=self.tenant_id,
                agent_id=self.agent_id,
                agent_version_id=self.version3_id,
                channel="webrtc",
                direction="inbound",
                purpose="qa",
                provider="ultravox",
                status="ended",
                ended_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            )
        )
        self.db.flush()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _version(self, version_id: str, number: int, status: str) -> TenantAgentVersion:
        return TenantAgentVersion(
            id=version_id,
            tenant_id=self.tenant_id,
            agent_id=self.agent_id,
            version=number,
            status=status,
            language="es-CO",
            identity_json={"name": f"Agent v{number}", "description": "Asesora"},
            instructions_json={"role": "Asesora", "objective": f"Objective v{number}", "system_prompt": "Prompt"},
            behavior_json={"response_style": "balanced"},
            runtime_binding_json={
                "tools": [{"key": "calendar.create_booking", "enabled": True, "config": {"api_key": "must-not-escape"}}],
                "realtime": {"provider": "ultravox", "api_key": "must-not-escape"},
            },
        )

    def _event(self, event_id: str, event_type: str, *, sequence=None, payload=None, source="livekit") -> None:
        self.db.add(
            VoiceSessionEvent(
                event_id=event_id,
                tenant_id=self.tenant_id,
                voice_session_id=self.session_id,
                event_type=event_type,
                source=source,
                sequence=sequence,
                payload_json=payload or {},
                occurred_at=datetime(2026, 10, 8, tzinfo=timezone.utc),
            )
        )

    def _complete_conversation(self):
        self._event("turn-assistant", "voice.transcript.final", sequence=2, payload={"speaker": "assistant", "text": "Le envié el resumen a persona@example.com"})
        self._event("turn-user", "voice.transcript.final", sequence=1, payload={"speaker": "user", "text": "Mi teléfono es +57 300 123 4567 y mi cédula 1234567890"})
        self._event("terminal", "voice.session.ended", payload={"transcript_final_sequence": 2}, source="voice-runtime")
        self._event("tool", "session.context.tool_used", payload={"tool_key": "calendar.create_booking", "status": "success", "duration_ms": 42, "arguments": {"secret": "drop"}})
        self.db.commit()

    def test_complete_snapshot_uses_exact_version_redacts_and_hashes_canonically(self) -> None:
        self._complete_conversation()
        conversation = VoiceSessionOperations(self.db).read_conversation_evidence(self.tenant_id, self.session_id)
        snapshot = AgentsFacade(self.db).read_evaluation_snapshot(self.tenant_id, conversation.agent_version_id)

        self.assertEqual(conversation.transcript_completeness, TranscriptCompleteness.COMPLETE)
        self.assertEqual([turn.sequence for turn in conversation.turns], [1, 2])
        self.assertEqual(snapshot.version, 3)
        self.assertEqual(snapshot.objective, "Objective v3")
        self.assertEqual(snapshot.enabled_tool_keys, ("calendar.create_booking",))
        self.assertNotIn("must-not-escape", repr(snapshot))

        evidence = build_semantic_evidence(conversation, snapshot)
        repeated = build_semantic_evidence(conversation, snapshot)
        self.assertEqual(evidence.evidence_hash, repeated.evidence_hash)
        self.assertEqual(evidence.agent_version_id, self.version3_id)
        self.assertNotIn("persona@example.com", repr(evidence))
        self.assertNotIn("300 123 4567", repr(evidence))
        self.assertNotIn("1234567890", repr(evidence))
        self.assertEqual(evidence.tool_outcomes[0].tool_key, "calendar.create_booking")
        self.assertNotIn("arguments", repr(evidence.tool_outcomes))

        changed = type(conversation)(**{
            **conversation.__dict__,
            "turns": (conversation.turns[0], type(conversation.turns[1])(
                **{**conversation.turns[1].__dict__, "text": "A different ordinary answer"}
            )),
        })
        self.assertNotEqual(build_semantic_evidence(changed, snapshot).evidence_hash, evidence.evidence_hash)

    def test_completeness_is_not_inferred_from_terminal_status(self) -> None:
        conversation = VoiceSessionOperations(self.db).read_conversation_evidence(self.tenant_id, self.session_id)
        self.assertEqual(conversation.transcript_completeness, TranscriptCompleteness.NOT_AVAILABLE)

        self._event("turn-1", "voice.transcript.final", sequence=1, payload={"speaker": "user", "text": "Hola"})
        self._event("terminal", "voice.session.ended", payload={"transcript_final_sequence": 2}, source="voice-runtime")
        self.db.commit()
        incomplete = VoiceSessionOperations(self.db).read_conversation_evidence(self.tenant_id, self.session_id)
        self.assertEqual(incomplete.transcript_completeness, TranscriptCompleteness.INCOMPLETE)
        with self.assertRaises(SemanticEvidenceUnavailableError):
            build_semantic_evidence(
                incomplete,
                AgentsFacade(self.db).read_evaluation_snapshot(self.tenant_id, self.version3_id),
            )

    def test_nonterminal_and_cross_tenant_reads_fail_closed(self) -> None:
        session = self.db.get(VoiceSession, self.session_id)
        session.status = "connected"
        self.db.commit()
        with self.assertRaises(VoiceConversationEvidenceNotReadyError):
            VoiceSessionOperations(self.db).read_conversation_evidence(self.tenant_id, self.session_id)
        with self.assertRaises(VoiceSessionNotFoundError):
            VoiceSessionOperations(self.db).read_conversation_evidence(str(uuid4()), self.session_id)

    def test_agent_reader_never_falls_back_to_latest_or_returns_runtime_credentials(self) -> None:
        reader = AgentsFacade(self.db)
        self.assertEqual(reader.read_evaluation_snapshot(self.tenant_id, self.version3_id).version, 3)
        self.db.delete(self.db.get(TenantAgentVersion, self.version3_id))
        self.db.commit()
        with self.assertRaises(AgentEvaluationSnapshotUnavailableError) as raised:
            reader.read_evaluation_snapshot(self.tenant_id, self.version3_id)
        self.assertEqual(raised.exception.code, "historical_evidence_missing")

    def test_duplicate_event_id_with_changed_payload_is_rejected(self) -> None:
        service = VoiceSessionService(self.db)
        session = self.db.get(VoiceSession, self.session_id)
        service.record_event(session, "voice.transcript.final", source="livekit", event_id="same-id", sequence=1, payload={"speaker": "user", "text": "Hola"}, commit=False)
        duplicate, is_duplicate = service.record_event(
            session,
            "voice.transcript.final",
            source="livekit",
            event_id="same-id",
            sequence=1,
            payload={"speaker": "user", "text": "Hola"},
            commit=False,
        )
        self.assertTrue(is_duplicate)
        self.assertEqual(duplicate.payload_json["text"], "Hola")
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "voice_event_id_payload_conflict"):
            service.record_event(
                session,
                "voice.transcript.final",
                source="livekit",
                event_id="same-id",
                sequence=1,
                payload={"speaker": "user", "text": "Adiós"},
                commit=False,
            )


class RedactionTests(unittest.TestCase):
    def test_business_numbers_survive(self) -> None:
        for text in (
            "Mi presupuesto es 300000000",
            "Presupuesto: $300.000.000",
            "El valor es 12500000 COP",
            "Ticket 12345678",
            "Referencia 20261008",
        ):
            self.assertEqual(redact_text(text), text)

    def test_structured_phones_are_redacted(self) -> None:
        for phone in ("+57 300 123 4567", "3001234567", "573001234567", "(300) 123-4567"):
            self.assertEqual(redact_text(f"Llame al {phone} hoy"), "Llame al [REDACTED_PHONE] hoy")


if __name__ == "__main__":
    unittest.main()
