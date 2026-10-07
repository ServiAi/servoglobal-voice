from __future__ import annotations

from datetime import datetime, timezone
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import Tenant
from app.modules.evaluations.domain.engine import evaluate
from app.modules.evaluations.domain.errors import EvaluationDefinitionVersionImmutable
from app.modules.evaluations.domain.technical_health import ToolOutcomeEvidence, VoiceSessionEvidence
from app.modules.evaluations.infrastructure.models import (
    CriterionResult,
    EvaluationDefinition,
    EvaluationDefinitionVersion,
    EvaluationRun,
    SYSTEM_OWNER_KEY,
)
from app.modules.evaluations.infrastructure.repositories import EvaluationRepository
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent

CRITERIA = [
    {"key": "session_terminal", "evaluator_type": "deterministic", "weight": 1},
    {"key": "runtime_health", "evaluator_type": "deterministic", "weight": 1},
    {"key": "tool_execution_health", "evaluator_type": "deterministic", "weight": 1},
]


class EvaluationCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.tenant_id = str(uuid4())
        self.definition_id = str(uuid4())
        self.version_id = str(uuid4())
        self.db.add(Tenant(id=self.tenant_id, name="Evaluation test", slug=f"eval-{self.tenant_id[:8]}"))
        self.db.add(EvaluationDefinition(
            id=self.definition_id, owner_scope="system", owner_key=SYSTEM_OWNER_KEY,
            tenant_id=None, definition_key="voice_session_technical_health",
            name="Voice session technical health", active=True,
        ))
        self.db.flush()
        self.db.add(EvaluationDefinitionVersion(
            id=self.version_id, definition_id=self.definition_id, owner_key=SYSTEM_OWNER_KEY,
            version=1, status="published", criteria_json=CRITERIA,
            published_at=datetime.now(timezone.utc),
        ))
        self.db.commit()
        self.repository = EvaluationRepository(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def evidence(self, *, status: str = "ended", tools=()) -> VoiceSessionEvidence:
        return VoiceSessionEvidence(
            tenant_id=self.tenant_id, session_id="session-1", purpose="qa", status=status,
            agent_version_id="agent-version-1", ended_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            error_code=None, tool_outcomes=tuple(tools),
        )

    def test_idempotent_request_and_conflicting_evidence_preserve_original(self) -> None:
        first = self.repository.request_voice_session(self.evidence(), trigger_key="terminal:1")
        same = self.repository.request_voice_session(self.evidence(), trigger_key="terminal:1")
        conflict = self.repository.request_voice_session(
            self.evidence(tools=[ToolOutcomeEvidence("calendar.create_booking", "error", 8, "timeout")]),
            trigger_key="terminal:1",
        )
        self.assertEqual(first.id, same.id)
        self.assertEqual(first.id, conflict.id)
        self.assertTrue(conflict.evidence_conflict)
        run = self.db.get(EvaluationRun, first.id)
        self.assertEqual(run.evidence_hash, first.evidence_hash)
        self.assertEqual(run.status, "queued")

    def test_worker_persists_deterministic_criteria_and_tenant_scoped_query(self) -> None:
        requested = self.repository.request_voice_session(self.evidence(), trigger_key="terminal:1")
        claim = self.repository.claim_batch(now=datetime.now(timezone.utc), lease_seconds=60, batch_size=10)[0]
        self.assertTrue(self.repository.execute(claim))
        result = self.repository.get(self.tenant_id, requested.id)
        self.assertEqual(result.run.status, "completed")
        self.assertTrue(result.run.passed)
        self.assertEqual({row.criterion_key for row in result.criteria}, {
            "session_terminal", "runtime_health", "tool_execution_health",
        })
        self.assertIsNone(self.repository.get(str(uuid4()), requested.id))

    def test_tool_failure_is_technical_failure_without_business_outcome_claim(self) -> None:
        evaluated = evaluate(CRITERIA, self.evidence(
            tools=[ToolOutcomeEvidence("calendar.create_booking", "error", 8, "timeout")]
        ))
        self.assertFalse(evaluated.passed)
        self.assertEqual(evaluated.score, 67)
        self.assertIn("tool_execution_health", {criterion.key for criterion in evaluated.criteria})

    def test_terminal_result_cannot_be_reclaimed_and_criterion_keys_are_unique(self) -> None:
        requested = self.repository.request_voice_session(self.evidence(), trigger_key="terminal:1")
        claim = self.repository.claim_batch(now=datetime.now(timezone.utc), lease_seconds=60, batch_size=1)[0]
        self.assertTrue(self.repository.execute(claim))
        self.assertEqual(self.repository.claim_batch(
            now=datetime.now(timezone.utc), lease_seconds=60, batch_size=1
        ), [])
        self.assertEqual(self.db.scalar(select(CriterionResult).where(
            CriterionResult.run_id == requested.id
        ).order_by(CriterionResult.criterion_key)).criterion_key, "runtime_health")

    def test_published_definition_version_is_immutable(self) -> None:
        version = self.db.get(EvaluationDefinitionVersion, self.version_id)
        version.criteria_json = []
        with self.assertRaisesRegex(EvaluationDefinitionVersionImmutable, "published_evaluation_definition_version_is_immutable"):
            self.db.flush()

    def test_voice_terminal_transition_durably_enqueues_and_rolls_back_atomically(self) -> None:
        session = VoiceSession(
            tenant_id=self.tenant_id, channel="web", direction="outbound", purpose="qa",
            provider="livekit", status="connected", agent_version_id="agent-version-1",
        )
        self.db.add(session)
        self.db.flush()
        event = VoiceSessionEvent(
            tenant_id=self.tenant_id, voice_session_id=session.id,
            event_type="session.context.tool_used", source="runtime",
            payload_json={"tool_key": "calendar.create_booking", "status": "error",
                          "duration_ms": 15, "error_code": "timeout"},
        )
        self.db.add(event)
        session.events.append(event)
        self.db.commit()

        VoiceSessionService(self.db).end(session, "normal")
        run = self.db.scalar(select(EvaluationRun).where(EvaluationRun.subject_id == session.id))
        self.assertEqual(run.status, "queued")
        self.assertEqual(run.agent_version_id, "agent-version-1")
        self.assertEqual(run.evidence_json["tool_outcomes"][0]["error_code"], "timeout")

        rollback_session = VoiceSession(
            tenant_id=self.tenant_id, channel="web", direction="outbound", purpose="qa",
            provider="livekit", status="connected",
        )
        self.db.add(rollback_session)
        self.db.flush()
        VoiceSessionService(self.db).transition(rollback_session, "cancelled", commit=False)
        self.db.rollback()
        self.assertIsNone(self.db.scalar(select(EvaluationRun).where(
            EvaluationRun.subject_id == rollback_session.id
        )))


if __name__ == "__main__":
    unittest.main()
