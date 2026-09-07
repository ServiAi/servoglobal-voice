from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path

TEST_DB_PATH = Path("serviai_migration_agent_builder_test.db")
os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models  # noqa: F401  (registers all mapped models on Base.metadata)
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.identity import Tenant
from app.models.integrations import TenantVoiceAgentConfig


def _load_migration(revision: str):
    path = (
        Path(__file__).parent
        / "alembic"
        / "versions"
        / f"{revision}_agent_builder_foundation.py"
    )
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_repair_migration(revision: str):
    path = (
        Path(__file__).parent
        / "alembic"
        / "versions"
        / f"{revision}_repair_agent_builder_draft_links.py"
    )
    spec = importlib.util.spec_from_file_location(f"migration_{revision}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentBuilderBackfillMigrationTests(unittest.TestCase):
    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        self.engine = create_engine(f"sqlite:///./{TEST_DB_PATH.as_posix()}")

        # SQLite ignores foreign keys unless explicitly told to enforce them;
        # without this, an insert-order bug like a circular FK violation
        # (caught for real only by Postgres) would pass here silently.
        @event.listens_for(self.engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.migration = _load_migration("202609060001")

    def tearDown(self):
        self.engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def _run_backfill(self):
        with self.engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                self.migration._backfill_from_voice_agent_configs()
            conn.commit()

    def test_backfills_active_config_into_published_agent(self):
        with self.Session() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            config = TenantVoiceAgentConfig(
                tenant_id=tenant.id,
                provider="ultravox",
                provider_agent_id="wk-agent-1",
                display_name="Sandra",
                description="Asesora comercial",
                purpose="Ventas",
                default_language="es",
                default_timezone="America/Bogota",
                default_system_prompt="Prompt legacy",
                status="active",
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            tenant_id, config_id = tenant.id, config.id

        self._run_backfill()

        with self.Session() as db:
            agent = db.scalar(select(TenantAgent).where(TenantAgent.tenant_id == tenant_id))
            self.assertIsNotNone(agent)
            self.assertEqual(agent.status, "active")
            self.assertIsNotNone(agent.published_version_id)
            version = db.get(TenantAgentVersion, agent.published_version_id)
            self.assertEqual(version.version, 1)
            self.assertEqual(version.status, "published")
            self.assertEqual(version.voice_agent_config_id, config_id)
            self.assertEqual(version.instructions_json["system_prompt"], "Prompt legacy")
            self.assertEqual(
                version.runtime_binding_json,
                {
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "ultravox"},
                },
            )
            # The legacy config itself is left untouched by the backfill.
            config = db.get(TenantVoiceAgentConfig, config_id)
            self.assertEqual(config.display_name, "Sandra")

    def test_inactive_config_backfills_as_draft(self):
        with self.Session() as db:
            tenant = Tenant(name="Tenant B", slug="tenant-b")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            config = TenantVoiceAgentConfig(
                tenant_id=tenant.id,
                provider="ultravox",
                provider_agent_id="wk-agent-2",
                display_name="Draft agent",
                status="inactive",
            )
            db.add(config)
            db.commit()
            tenant_id = tenant.id

        self._run_backfill()

        with self.Session() as db:
            agent = db.scalar(select(TenantAgent).where(TenantAgent.tenant_id == tenant_id))
            self.assertIsNotNone(agent)
            self.assertEqual(agent.status, "draft")
            self.assertIsNone(agent.published_version_id)
            version = db.scalar(
                select(TenantAgentVersion).where(TenantAgentVersion.agent_id == agent.id)
            )
            self.assertEqual(version.status, "draft")
            self.assertIsNone(version.published_at)
            self.assertEqual(agent.draft_version_id, version.id)

    def test_noop_when_no_configs_exist(self):
        self._run_backfill()
        with self.Session() as db:
            self.assertIsNone(db.scalar(select(TenantAgent)))


class AgentBuilderDraftLinkRepairMigrationTests(unittest.TestCase):
    """Covers 202609070001, which repairs agents left by an older run of the
    202609060001 backfill (before it wrote draft_version_id itself)."""

    def setUp(self):
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        self.engine = create_engine(f"sqlite:///./{TEST_DB_PATH.as_posix()}")

        @event.listens_for(self.engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.repair = _load_repair_migration("202609070001")

    def tearDown(self):
        self.engine.dispose()
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def _run_repair(self):
        with self.engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx):
                self.repair._repair_missing_draft_links()
            conn.commit()

    def _seed_broken_draft_agent(self, tenant_slug: str) -> tuple[str, str]:
        with self.Session() as db:
            tenant = Tenant(name=tenant_slug, slug=tenant_slug)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = TenantAgent(
                tenant_id=tenant.id,
                name="Broken draft agent",
                status="draft",
                published_version_id=None,
                draft_version_id=None,
            )
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                agent_id=agent.id,
                tenant_id=tenant.id,
                version=1,
                status="draft",
                identity_json={"name": "Broken draft agent", "description": None},
                instructions_json={
                    "role": "",
                    "objective": "",
                    "system_prompt": "",
                    "greeting": "",
                    "closing": "",
                },
                behavior_json={
                    "response_style": "balanced",
                    "interruptions": "balanced",
                    "turn_detection": "automatic",
                    "confirmation_strategy": "important_data",
                    "agent_first": True,
                },
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "ultravox"},
                },
            )
            db.add(version)
            db.commit()
            db.refresh(agent)
            db.refresh(version)
            return agent.id, version.id

    def test_repairs_draft_agent_missing_draft_version_id(self):
        agent_id, version_id = self._seed_broken_draft_agent("tenant-repair-a")
        self._run_repair()
        with self.Session() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertEqual(agent.draft_version_id, version_id)

    def test_repair_is_idempotent(self):
        agent_id, version_id = self._seed_broken_draft_agent("tenant-repair-b")
        self._run_repair()
        self._run_repair()
        with self.Session() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertEqual(agent.draft_version_id, version_id)

    def test_does_not_overwrite_existing_draft_version_id(self):
        with self.Session() as db:
            tenant = Tenant(name="tenant-repair-c", slug="tenant-repair-c")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = TenantAgent(tenant_id=tenant.id, name="Agent", status="draft")
            db.add(agent)
            db.flush()
            correct_version = TenantAgentVersion(
                agent_id=agent.id,
                tenant_id=tenant.id,
                version=1,
                status="draft",
                identity_json={"name": "Agent", "description": None},
                instructions_json={
                    "role": "",
                    "objective": "",
                    "system_prompt": "",
                    "greeting": "",
                    "closing": "",
                },
                behavior_json={
                    "response_style": "balanced",
                    "interruptions": "balanced",
                    "turn_detection": "automatic",
                    "confirmation_strategy": "important_data",
                    "agent_first": True,
                },
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "ultravox"},
                },
            )
            db.add(correct_version)
            db.flush()
            agent.draft_version_id = correct_version.id
            db.commit()
            agent_id, correct_version_id = agent.id, correct_version.id

        self._run_repair()

        with self.Session() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertEqual(agent.draft_version_id, correct_version_id)

    def test_does_not_touch_archived_agents(self):
        with self.Session() as db:
            tenant = Tenant(name="tenant-repair-d", slug="tenant-repair-d")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = TenantAgent(
                tenant_id=tenant.id, name="Archived agent", status="archived"
            )
            db.add(agent)
            db.commit()
            agent_id = agent.id

        self._run_repair()

        with self.Session() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertIsNone(agent.draft_version_id)

    def test_falls_closed_when_multiple_draft_versions_exist(self):
        # Not producible by any real flow today (AgentService enforces one
        # editable draft per agent), but the migration must not guess if
        # data is ever found in this shape.
        with self.Session() as db:
            tenant = Tenant(name="tenant-repair-e", slug="tenant-repair-e")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            agent = TenantAgent(tenant_id=tenant.id, name="Ambiguous agent", status="draft")
            db.add(agent)
            db.flush()
            for version_number in (1, 2):
                db.add(
                    TenantAgentVersion(
                        agent_id=agent.id,
                        tenant_id=tenant.id,
                        version=version_number,
                        status="draft",
                        identity_json={"name": "Ambiguous agent", "description": None},
                        instructions_json={
                            "role": "",
                            "objective": "",
                            "system_prompt": "",
                            "greeting": "",
                            "closing": "",
                        },
                        behavior_json={
                            "response_style": "balanced",
                            "interruptions": "balanced",
                            "turn_detection": "automatic",
                            "confirmation_strategy": "important_data",
                            "agent_first": True,
                        },
                        runtime_binding_json={
                            "pipeline_type": "realtime",
                            "realtime": {"provider": "ultravox", "model": "ultravox"},
                        },
                    )
                )
            db.commit()
            agent_id = agent.id

        self._run_repair()

        with self.Session() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertIsNone(agent.draft_version_id)


if __name__ == "__main__":
    unittest.main()
