from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import threading
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.db.base import Base
from app.models import Tenant
from app.modules.evaluations.domain.technical_health import VoiceSessionEvidence
from app.modules.evaluations.infrastructure.models import (
    CriterionResult,
    EvaluationDefinition,
    EvaluationDefinitionVersion,
    EvaluationRun,
    SYSTEM_OWNER_KEY,
)
from app.modules.evaluations.infrastructure.repositories import EvaluationRepository

_CRITERIA = [
    {"key": "session_terminal", "evaluator_type": "deterministic", "weight": 1},
    {"key": "runtime_health", "evaluator_type": "deterministic", "weight": 1},
    {"key": "tool_execution_health", "evaluator_type": "deterministic", "weight": 1},
]


class EvaluationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        raw = os.environ.get("EVALUATIONS_TEST_DATABASE_URL")
        if not raw:
            raise unittest.SkipTest("EVALUATIONS_TEST_DATABASE_URL is required for PostgreSQL invariants")
        url = make_url(raw)
        if not url.database or not url.database.endswith("_evaluations_test"):
            raise RuntimeError("Refusing destructive setup outside an *_evaluations_test database")
        cls.engine = create_engine(raw, pool_pre_ping=True)
        Base.metadata.drop_all(cls.engine)
        Base.metadata.create_all(cls.engine)
        with cls.engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE OR REPLACE FUNCTION prevent_published_evaluation_version_mutation() RETURNS trigger AS $$
                BEGIN
                    IF OLD.status = 'published' THEN
                        RAISE EXCEPTION 'published_evaluation_definition_version_is_immutable';
                    END IF;
                    IF TG_OP = 'DELETE' THEN
                        RETURN OLD;
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            conn.exec_driver_sql("""
                CREATE TRIGGER trg_published_evaluation_version_immutable
                BEFORE UPDATE OR DELETE ON evaluation_definition_versions
                FOR EACH ROW EXECUTE FUNCTION prevent_published_evaluation_version_mutation()
            """)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "engine"):
            with cls.engine.begin() as conn:
                conn.exec_driver_sql("DROP TRIGGER IF EXISTS trg_published_evaluation_version_immutable ON evaluation_definition_versions")
                conn.exec_driver_sql("DROP FUNCTION IF EXISTS prevent_published_evaluation_version_mutation()")
            Base.metadata.drop_all(cls.engine)
            cls.engine.dispose()

    def setUp(self) -> None:
        with Session(self.engine) as db:
            db.execute(delete(EvaluationRun))
            db.execute(delete(Tenant))
            db.commit()

    def seeded(self) -> tuple[str, str]:
        tenant_id = str(uuid4())
        with Session(self.engine) as db:
            db.add(Tenant(id=tenant_id, name="Evaluation PostgreSQL test", slug=f"eval-{tenant_id[:8]}"))
            db.flush()
            definition = db.scalar(select(EvaluationDefinition).where(
                EvaluationDefinition.owner_key == SYSTEM_OWNER_KEY,
                EvaluationDefinition.definition_key == "voice_session_technical_health",
            ))
            if definition is None:
                definition = EvaluationDefinition(
                    id=str(uuid4()), owner_scope="system", owner_key=SYSTEM_OWNER_KEY,
                    definition_key="voice_session_technical_health", name="Technical health", active=True,
                )
                db.add(definition)
                db.flush()
            version = db.scalar(select(EvaluationDefinitionVersion).where(
                EvaluationDefinitionVersion.definition_id == definition.id,
                EvaluationDefinitionVersion.version == 1,
            ))
            if version is None:
                version = EvaluationDefinitionVersion(
                    id=str(uuid4()), definition_id=definition.id, owner_key=SYSTEM_OWNER_KEY,
                    version=1, status="published", criteria_json=_CRITERIA,
                    published_at=datetime.now(timezone.utc),
                )
                db.add(version)
                db.flush()
            version_id = version.id
            db.commit()
        return tenant_id, version_id

    def evidence(self, tenant_id: str, session_id: str) -> VoiceSessionEvidence:
        return VoiceSessionEvidence(
            tenant_id=tenant_id, session_id=session_id, purpose="production", status="ended",
            agent_version_id="historical-agent-version", ended_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            error_code=None, tool_outcomes=(),
        )

    def request(self, tenant_id: str, session_id: str, trigger: str = "terminal:event"):
        with Session(self.engine) as db:
            result = EvaluationRepository(db).request_voice_session(
                self.evidence(tenant_id, session_id), trigger_key=trigger
            )
            db.commit()
            return result

    def test_concurrent_duplicate_delivery_and_conflicting_hash(self) -> None:
        tenant_id, _ = self.seeded()
        barrier = threading.Barrier(2)

        def submit():
            barrier.wait()
            return self.request(tenant_id, "session-duplicate")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = [future.result() for future in [pool.submit(submit), pool.submit(submit)]]
        self.assertEqual(first.id, second.id)
        changed = self.evidence(tenant_id, "session-duplicate")
        changed = VoiceSessionEvidence(**{**changed.__dict__, "status": "failed", "error_code": "runtime_error"})
        with Session(self.engine) as db:
            conflict = EvaluationRepository(db).request_voice_session(changed, trigger_key="terminal:event")
            db.commit()
        self.assertEqual(conflict.id, first.id)
        self.assertTrue(conflict.evidence_conflict)
        with Session(self.engine) as db:
            stored = db.get(EvaluationRun, first.id)
            self.assertEqual(stored.evidence_hash, first.evidence_hash)
            self.assertEqual(stored.status, "queued")

    def test_two_workers_claim_once_and_stale_owner_cannot_complete(self) -> None:
        tenant_id, _ = self.seeded()
        run = self.request(tenant_id, "session-claim")
        at = datetime.now(timezone.utc)
        barrier = threading.Barrier(2)

        def claim():
            with Session(self.engine) as db:
                barrier.wait()
                return EvaluationRepository(db).claim_batch(now=at, lease_seconds=1, batch_size=1)

        with ThreadPoolExecutor(max_workers=2) as pool:
            claim_sets = [f.result() for f in [pool.submit(claim), pool.submit(claim)]]
        first_claim = next(row for rows in claim_sets for row in rows)
        self.assertEqual(sum(map(len, claim_sets)), 1)
        with Session(self.engine) as db:
            second_claims = EvaluationRepository(db).claim_batch(
                now=at + timedelta(seconds=2), lease_seconds=30, batch_size=1
            )
        self.assertEqual(len(second_claims), 1)
        with Session(self.engine) as db:
            self.assertFalse(EvaluationRepository(db).execute(first_claim, now=at + timedelta(seconds=3)))
        with Session(self.engine) as db:
            self.assertTrue(EvaluationRepository(db).execute(second_claims[0], now=at + timedelta(seconds=3)))
            self.assertEqual(db.scalar(select(EvaluationRun.status).where(EvaluationRun.id == run.id)), "completed")
            self.assertEqual(db.scalar(select(func.count()).select_from(CriterionResult).where(
                CriterionResult.tenant_id == tenant_id, CriterionResult.run_id == run.id
            )), 3)

    def test_transient_retry_is_bounded_and_tenant_queries_fail_closed(self) -> None:
        tenant_id, _ = self.seeded()
        run = self.request(tenant_id, "session-retry")
        at = datetime.now(timezone.utc)
        with Session(self.engine) as db:
            claim = EvaluationRepository(db).claim_batch(now=at, lease_seconds=30, batch_size=1)[0]
        with Session(self.engine) as db:
            self.assertTrue(EvaluationRepository(db)._record_failure(
                claim, now=at + timedelta(seconds=1), code="temporary_db_error", retryable=True
            ))
            stored = db.get(EvaluationRun, run.id)
            self.assertEqual(stored.status, "queued")
            self.assertEqual(stored.attempt_count, 1)
        with Session(self.engine) as db:
            self.assertIsNone(EvaluationRepository(db).get(str(uuid4()), run.id))

    def test_completed_results_are_atomic_unique_and_late_cancelled_claim_is_rejected(self) -> None:
        tenant_id, version_id = self.seeded()
        run = self.request(tenant_id, "session-atomic")
        at = datetime.now(timezone.utc)
        with Session(self.engine) as db:
            self.assertEqual(db.get(EvaluationRun, run.id).definition_version_id, version_id)
            claim = EvaluationRepository(db).claim_batch(now=at, lease_seconds=30, batch_size=1)[0]
            current = db.get(EvaluationRun, run.id)
            current.status = "cancelled"
            db.commit()
        with Session(self.engine) as db:
            self.assertFalse(EvaluationRepository(db).execute(claim, now=at + timedelta(seconds=1)))
            self.assertEqual(db.scalar(select(func.count()).select_from(CriterionResult).where(
                CriterionResult.run_id == run.id
            )), 0)

        another = self.request(tenant_id, "session-atomic-success", trigger="terminal:success")
        with Session(self.engine) as db:
            repo = EvaluationRepository(db)
            claim = repo.claim_batch(now=at, lease_seconds=30, batch_size=1)[0]
            self.assertTrue(repo.execute(claim, now=at + timedelta(seconds=1)))
            first = db.scalar(select(CriterionResult).where(CriterionResult.run_id == another.id))
            db.add(CriterionResult(
                tenant_id=tenant_id, run_id=another.id, criterion_key=first.criterion_key,
                evaluator_type="deterministic", implementation_version="deterministic-v1",
                passed=first.passed, score=first.score, reason=first.reason, evidence_ref_json=first.evidence_ref_json,
            ))
            with self.assertRaises(IntegrityError):
                db.flush()

    def test_published_version_trigger_and_owner_constraints(self) -> None:
        tenant_id, version_id = self.seeded()
        with Session(self.engine) as db:
            with self.assertRaisesRegex(Exception, "published_evaluation_definition_version_is_immutable"):
                db.execute(text("UPDATE evaluation_definition_versions SET criteria_json = '[]'::json WHERE id = :id"),
                           {"id": version_id})
            db.rollback()
            self.assertEqual(db.get(EvaluationDefinitionVersion, version_id).status, "published")
            # Tenant-owned definitions cannot be attached to another tenant's run.
            tenant_definition_id, tenant_version_id = str(uuid4()), str(uuid4())
            db.add(EvaluationDefinition(
                id=tenant_definition_id, owner_scope="tenant", owner_key=tenant_id,
                tenant_id=tenant_id, definition_key="tenant_test", name="Tenant test", active=True,
            ))
            db.flush()
            db.add(EvaluationDefinitionVersion(
                id=tenant_version_id, definition_id=tenant_definition_id, owner_key=tenant_id,
                version=1, status="published", criteria_json=_CRITERIA,
                published_at=datetime.now(timezone.utc),
            ))
            db.flush()
            foreign_tenant = str(uuid4())
            db.add(Tenant(id=foreign_tenant, name="Foreign tenant", slug=f"eval-{foreign_tenant[:8]}"))
            db.flush()
            db.add(EvaluationRun(
                tenant_id=foreign_tenant, owner_key=tenant_id, subject_type="voice_session",
                subject_id="foreign-session", agent_version_id=None, definition_version_id=tenant_version_id,
                source="test", trigger_key="foreign-trigger", status="queued", evidence_hash="a" * 64,
                evidence_json={},
            ))
            with self.assertRaises(IntegrityError):
                db.flush()


if __name__ == "__main__":
    unittest.main()
