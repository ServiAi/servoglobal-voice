from __future__ import annotations

import importlib.util
import os
import unittest
import uuid
from pathlib import Path

TEST_DB_PATH = Path("serviai_migration_backfill_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from app.db.base import Base
import app.models  # noqa: F401  (registers all mapped models on Base.metadata)


def _load_migration(revision: str):
    path = (
        Path(__file__).parent
        / "alembic"
        / "versions"
        / f"{revision}_backfill_call_agent_ids.py"
    )
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BackfillCallAgentIdsMigrationTests(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        self.engine = create_engine(f"sqlite:///./{TEST_DB_PATH.as_posix()}")
        Base.metadata.create_all(self.engine)
        self.migration = _load_migration("202608180002")

    def tearDown(self):
        self.engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def _run_migration(self):
        with self.engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                self.migration.upgrade()
            conn.commit()

    def test_backfills_only_calls_matching_an_existing_agent(self):
        tenant_id = str(uuid.uuid4())
        matched_call_id = str(uuid.uuid4())
        unmatched_call_id = str(uuid.uuid4())
        already_set_call_id = str(uuid.uuid4())
        agent_id = str(uuid.uuid4())
        other_agent_id = str(uuid.uuid4())

        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tenants (id, slug, name, timezone, status, created_at, updated_at) "
                    "VALUES (:id, :slug, :name, 'America/Bogota', 'active', datetime('now'), datetime('now'))"
                ),
                {"id": tenant_id, "slug": f"tenant-{tenant_id[:8]}", "name": "Backfill Tenant"},
            )
            conn.execute(
                text(
                    "INSERT INTO agents (id, tenant_id, external_provider, external_agent_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, 'ultravox', 'wk-agent-123', 'Agente Comercial', 'active', datetime('now'), datetime('now'))"
                ),
                {"id": agent_id, "tenant_id": tenant_id},
            )
            conn.execute(
                text(
                    "INSERT INTO agents (id, tenant_id, external_provider, external_agent_id, name, status, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, 'ultravox', 'wk-agent-999', 'Otro Agente', 'active', datetime('now'), datetime('now'))"
                ),
                {"id": other_agent_id, "tenant_id": tenant_id},
            )
            # A call ingested before the agent existed: agent_id is NULL but
            # provider_agent_id records who actually took it.
            conn.execute(
                text(
                    "INSERT INTO calls (id, tenant_id, external_provider, external_call_id, agent_id, provider_agent_id, "
                    "normalized_status, started_at, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, 'ultravox', 'ext-1', NULL, 'wk-agent-123', 'answered', datetime('now'), datetime('now'), datetime('now'))"
                ),
                {"id": matched_call_id, "tenant_id": tenant_id},
            )
            # A call whose provider_agent_id doesn't match any known agent:
            # must stay untouched rather than being pointed at the wrong one.
            conn.execute(
                text(
                    "INSERT INTO calls (id, tenant_id, external_provider, external_call_id, agent_id, provider_agent_id, "
                    "normalized_status, started_at, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, 'ultravox', 'ext-2', NULL, 'wk-agent-does-not-exist', 'answered', datetime('now'), datetime('now'), datetime('now'))"
                ),
                {"id": unmatched_call_id, "tenant_id": tenant_id},
            )
            # A call that already resolved correctly at ingestion time: must
            # not be reassigned even though a different agent also exists.
            conn.execute(
                text(
                    "INSERT INTO calls (id, tenant_id, external_provider, external_call_id, agent_id, provider_agent_id, "
                    "normalized_status, started_at, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, 'ultravox', 'ext-3', :agent_id, 'wk-agent-999', 'answered', datetime('now'), datetime('now'), datetime('now'))"
                ),
                {"id": already_set_call_id, "tenant_id": tenant_id, "agent_id": other_agent_id},
            )

        self._run_migration()

        with self.engine.connect() as conn:
            rows = {
                row.id: row.agent_id
                for row in conn.execute(text("SELECT id, agent_id FROM calls"))
            }
        self.assertEqual(rows[matched_call_id], agent_id)
        self.assertIsNone(rows[unmatched_call_id])
        self.assertEqual(rows[already_set_call_id], other_agent_id)

    def test_noop_when_no_calls_need_backfill(self):
        # Nothing to update; must not raise.
        self._run_migration()
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT COUNT(*) FROM calls")).scalar(), 0)


if __name__ == "__main__":
    unittest.main()
