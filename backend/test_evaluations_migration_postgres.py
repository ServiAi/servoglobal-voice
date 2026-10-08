r"""Real PostgreSQL migration tests for 202610080001 (semantic evaluation engine).

Needs its own disposable database (the schema is rebuilt with Alembic from scratch):

    $env:EVALUATIONS_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_evaluations_migration_test"
    .\.venv\Scripts\python.exe -m unittest test_evaluations_migration_postgres -v
"""

from __future__ import annotations

import json
import os
import unittest
from uuid import uuid4

MIGRATION_TEST_DATABASE_URL = os.environ.get("EVALUATIONS_MIGRATION_TEST_DATABASE_URL")
if MIGRATION_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ["DATABASE_URL"] = MIGRATION_TEST_DATABASE_URL

from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from alembic import command

BEFORE = "202610070001"
AFTER = "202610080001"
SEMANTIC_VERSION_ID = "00000000-0000-4000-8000-000000000015"


def _config() -> Config:
    return Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))


@unittest.skipUnless(
    MIGRATION_TEST_DATABASE_URL,
    "EVALUATIONS_MIGRATION_TEST_DATABASE_URL not set; skipping real PostgreSQL migration tests",
)
class SemanticEvaluationEngineMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(MIGRATION_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("EVALUATIONS_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        with cls.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(_config(), BEFORE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        if self._revision() != BEFORE:
            command.downgrade(_config(), BEFORE)
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM evaluation_runs"))
            conn.execute(text("DELETE FROM tenants"))

    def _revision(self) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

    def _columns(self) -> dict[str, str]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'evaluation_criterion_results'"
            ))
            return {name: nullable for name, nullable in rows}

    def _legacy_run_with_results(self) -> tuple[str, str]:
        """A completed technical run whose results predate outcome/provenance."""
        tenant_id, run_id = str(uuid4()), str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenants (id, name, slug, timezone, status) VALUES (:id, 'T', :slug, 'UTC', 'active')"),
                {"id": tenant_id, "slug": f"mig-{uuid4().hex[:10]}"},
            )
            version_id = conn.execute(text(
                "SELECT v.id FROM evaluation_definition_versions v JOIN evaluation_definitions d ON d.id = v.definition_id "
                "WHERE d.definition_key = 'voice_session_technical_health'"
            )).scalar()
            conn.execute(text(
                "INSERT INTO evaluation_runs (id, tenant_id, owner_key, subject_type, subject_id, definition_version_id, "
                "source, trigger_key, status, evidence_hash, evidence_json) VALUES "
                "(:id, :t, '__system__', 'voice_session', 'legacy', :v, 'voice_terminal', 'legacy', 'completed', "
                ":h, '{}')"
            ), {"id": run_id, "t": tenant_id, "v": version_id, "h": "a" * 64})
            for key, passed in (("session_terminal", True), ("runtime_health", False)):
                conn.execute(text(
                    "INSERT INTO evaluation_criterion_results (id, tenant_id, run_id, criterion_key, evaluator_type, "
                    "implementation_version, passed, score, reason) VALUES "
                    "(:id, :t, :r, :k, 'deterministic', 'deterministic-v1', :p, :s, 'legacy')"
                ), {"id": str(uuid4()), "t": tenant_id, "r": run_id, "k": key, "p": passed, "s": 100 if passed else 0})
        return tenant_id, run_id

    def _insert_result(self, conn, tenant_id: str, run_id: str, key: str, *, outcome, passed, score,
                       evaluator_type="llm", provenance="{}") -> None:
        conn.execute(text(
            "INSERT INTO evaluation_criterion_results (id, tenant_id, run_id, criterion_key, evaluator_type, "
            "implementation_version, outcome, passed, score, reason, provenance_json) VALUES "
            "(:id, :t, :r, :k, :e, 'v', :o, :p, :s, 'r', CAST(:prov AS json))"
        ), {"id": str(uuid4()), "t": tenant_id, "r": run_id, "k": key, "e": evaluator_type, "o": outcome,
            "p": passed, "s": score, "prov": provenance})

    def test_upgrade_backfills_legacy_rows_without_inventing_semantics(self) -> None:
        tenant_id, run_id = self._legacy_run_with_results()
        command.upgrade(_config(), AFTER)
        self.assertEqual(self._revision(), AFTER)
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT criterion_key, outcome, passed, verdict, provenance_json FROM evaluation_criterion_results "
                "WHERE run_id = :r ORDER BY criterion_key"
            ), {"r": run_id}).all()
        self.assertEqual([(r[0], r[1], r[2], r[3], r[4]) for r in rows], [
            ("runtime_health", "fail", False, None, None),
            ("session_terminal", "pass", True, None, None),
        ])
        columns = self._columns()
        self.assertEqual((columns["outcome"], columns["passed"], columns["provenance_json"]),
                         ("NO", "YES", "YES"))

    def test_constraints_reject_inconsistent_outcome_passed_score_and_provenance(self) -> None:
        tenant_id, run_id = self._legacy_run_with_results()
        command.upgrade(_config(), AFTER)
        valid = [
            ("a", "pass", True, 90), ("b", "fail", False, 10), ("c", "insufficient_evidence", None, None),
        ]
        with self.engine.begin() as conn:
            for key, outcome, passed, score in valid:
                self._insert_result(conn, tenant_id, run_id, key, outcome=outcome, passed=passed, score=score)
        invalid = [
            ("pass", False, 90, "llm", "{}"),
            ("fail", True, 10, "llm", "{}"),
            ("pass", None, 90, "llm", "{}"),
            ("insufficient_evidence", False, None, "llm", "{}"),
            ("insufficient_evidence", True, 50, "llm", "{}"),
            ("insufficient_evidence", None, 50, "llm", "{}"),
            ("unknown", True, 90, "llm", "{}"),
        ]
        for index, (outcome, passed, score, evaluator, provenance) in enumerate(invalid):
            with self.assertRaises(DBAPIError, msg=str((outcome, passed, score))):
                with self.engine.begin() as conn:
                    self._insert_result(conn, tenant_id, run_id, f"bad-{index}", outcome=outcome, passed=passed,
                                        score=score, evaluator_type=evaluator, provenance=provenance)
        # SQL NULL provenance (not JSON null) on an llm row is what the constraint forbids.
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO evaluation_criterion_results (id, tenant_id, run_id, criterion_key, evaluator_type, "
                    "implementation_version, outcome, passed, score, reason) VALUES "
                    "(:id, :t, :r, 'nullprov', 'llm', 'v', 'pass', true, 90, 'r')"
                ), {"id": str(uuid4()), "t": tenant_id, "r": run_id})

    def test_semantic_definition_is_seeded_published_and_immutable(self) -> None:
        command.upgrade(_config(), AFTER)
        from app.modules.evaluations.domain.semantic_definition import (
            semantic_quality_criteria,
        )

        with self.engine.connect() as conn:
            row = conn.execute(text(
                "SELECT d.definition_key, d.owner_scope, v.version, v.status, v.criteria_json "
                "FROM evaluation_definition_versions v JOIN evaluation_definitions d ON d.id = v.definition_id "
                "WHERE v.id = :id"
            ), {"id": SEMANTIC_VERSION_ID}).one()
        self.assertEqual(row[:4], ("voice_session_semantic_quality", "system", 1, "published"))
        criteria = row[4] if isinstance(row[4], list) else json.loads(row[4])
        self.assertEqual(criteria, semantic_quality_criteria())
        self.assertEqual([c["evaluator_type"] for c in criteria], ["llm"] * 3)
        with self.assertRaisesRegex(Exception, "published_evaluation_definition_version_is_immutable"):
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE evaluation_definition_versions SET criteria_json = '[]'::json WHERE id = :id"),
                             {"id": SEMANTIC_VERSION_ID})

    def test_downgrade_removes_semantic_artifacts_and_keeps_deterministic_rows(self) -> None:
        tenant_id, run_id = self._legacy_run_with_results()
        command.upgrade(_config(), AFTER)
        with self.engine.begin() as conn:
            self._insert_result(conn, tenant_id, run_id, "insufficient", outcome="insufficient_evidence",
                                passed=None, score=None)
        command.downgrade(_config(), BEFORE)
        self.assertEqual(self._revision(), BEFORE)
        self.assertEqual(self._columns()["passed"], "NO")
        self.assertNotIn("outcome", self._columns())
        with self.engine.connect() as conn:
            keys = [r[0] for r in conn.execute(text(
                "SELECT criterion_key FROM evaluation_criterion_results WHERE run_id = :r ORDER BY criterion_key"
            ), {"r": run_id})]
            definitions = conn.execute(text(
                "SELECT count(*) FROM evaluation_definitions WHERE definition_key = 'voice_session_semantic_quality'"
            )).scalar()
        self.assertEqual(keys, ["runtime_health", "session_terminal"])
        self.assertEqual(definitions, 0)
        command.upgrade(_config(), AFTER)  # re-applies cleanly
        self.assertEqual(self._revision(), AFTER)


if __name__ == "__main__":
    unittest.main()
