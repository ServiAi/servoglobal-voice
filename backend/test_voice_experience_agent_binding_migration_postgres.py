"""PostgreSQL migration gate for the Voice Experience canonical binding revision.

Run only with a disposable database:
    $env:VOICE_EXPERIENCE_BINDING_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://.../voice_binding_migration_test"
    python -m unittest test_voice_experience_agent_binding_migration_postgres -v
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import ForeignKey, MetaData, String, Table, Column, DateTime, create_engine, select, text
from alembic.migration import MigrationContext
from alembic.operations import Operations


DATABASE_URL = os.environ.get("VOICE_EXPERIENCE_BINDING_MIGRATION_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parent / "alembic" / "versions" / "202610090001_voice_experience_canonical_agent_binding.py"


@unittest.skipUnless(
    DATABASE_URL,
    "VOICE_EXPERIENCE_BINDING_MIGRATION_TEST_DATABASE_URL not set; skipping PostgreSQL migration tests",
)
class VoiceExperienceCanonicalBindingMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("VOICE_EXPERIENCE_BINDING_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        spec = importlib.util.spec_from_file_location("voice_binding_migration", MIGRATION_PATH)
        assert spec and spec.loader
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.schema = "ve134_" + uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self._connect_schema()

    def tearDown(self) -> None:
        self.connection.close()
        with self.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))

    def _connect_schema(self) -> None:
        if getattr(self, "connection", None) is not None:
            self.connection.close()
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql(f'SET search_path TO "{self.schema}"')
        self.connection.commit()
        metadata = MetaData()
        Table("tenant_agents", metadata,
              Column("id", String(36), primary_key=True), Column("tenant_id", String(36), nullable=False))
        Table("tenant_agent_versions", metadata,
              Column("id", String(36), primary_key=True),
              Column("agent_id", String(36), ForeignKey("tenant_agents.id"), nullable=False),
              Column("tenant_id", String(36), nullable=False), Column("status", String(16), nullable=False),
              Column("voice_agent_config_id", String(36), nullable=True),
              Column("published_at", DateTime(timezone=True), nullable=True))
        Table("tenant_voice_experiences", metadata,
              Column("id", String(36), primary_key=True), Column("tenant_id", String(36), nullable=False),
              Column("agent_config_id", String(36), nullable=False))
        Table("tenant_voice_experience_versions", metadata,
              Column("id", String(36), primary_key=True),
              Column("experience_id", String(36), ForeignKey("tenant_voice_experiences.id"), nullable=False),
              Column("tenant_id", String(36), nullable=False), Column("agent_config_id", String(36), nullable=False),
              Column("published_at", DateTime(timezone=True), nullable=False))
        metadata.create_all(self.connection)
        self.connection.commit()

    def _upgrade(self) -> None:
        if self.connection.in_transaction():
            self.connection.commit()
        with self.connection.begin():
            with Operations.context(MigrationContext.configure(self.connection)):
                self.migration.upgrade()

    def _downgrade(self) -> None:
        if self.connection.in_transaction():
            self.connection.commit()
        with self.connection.begin():
            with Operations.context(MigrationContext.configure(self.connection)):
                self.migration.downgrade()

    def _agent(self, tenant_id: str, configs: tuple[tuple[str, str, datetime | None], ...]) -> tuple[str, list[str]]:
        agent_id = str(uuid4())
        self.connection.execute(text("INSERT INTO tenant_agents (id, tenant_id) VALUES (:id, :tenant)"),
                                {"id": agent_id, "tenant": tenant_id})
        version_ids = []
        for status, config_id, published_at in configs:
            version_id = str(uuid4())
            self.connection.execute(text(
                "INSERT INTO tenant_agent_versions (id, agent_id, tenant_id, status, voice_agent_config_id, published_at) "
                "VALUES (:id, :agent, :tenant, :status, :config, :published_at)"
            ), {"id": version_id, "agent": agent_id, "tenant": tenant_id, "status": status,
                "config": config_id, "published_at": published_at})
            version_ids.append(version_id)
        return agent_id, version_ids

    def _experience(self, tenant_id: str, config_id: str, versions: tuple[tuple[str, datetime], ...]) -> tuple[str, list[str]]:
        experience_id = str(uuid4())
        self.connection.execute(text(
            "INSERT INTO tenant_voice_experiences (id, tenant_id, agent_config_id) VALUES (:id, :tenant, :config)"
        ), {"id": experience_id, "tenant": tenant_id, "config": config_id})
        version_ids = []
        for config, published_at in versions:
            version_id = str(uuid4())
            self.connection.execute(text(
                "INSERT INTO tenant_voice_experience_versions (id, experience_id, tenant_id, agent_config_id, published_at) "
                "VALUES (:id, :experience, :tenant, :config, :published_at)"
            ), {"id": version_id, "experience": experience_id, "tenant": tenant_id,
                "config": config, "published_at": published_at})
            version_ids.append(version_id)
        return experience_id, version_ids

    def test_backfills_exact_temporal_history_and_survives_downgrade_reupgrade(self) -> None:
        tenant_id, config_x, config_y = (str(uuid4()) for _ in range(3))
        t1 = datetime(2026, 1, 1, tzinfo=UTC)
        t2 = datetime(2026, 2, 1, tzinfo=UTC)
        agent_a, (a1, a2) = self._agent(tenant_id, (("superseded", config_x, t1), ("published", config_x, t2)))
        agent_b, (b1,) = self._agent(tenant_id, (("published", config_y, t1),))
        experience_a, (before, between, after) = self._experience(
            tenant_id, config_x,
            ((config_x, t1 - timedelta(days=1)), (config_x, t1 + timedelta(days=1)), (config_x, t2 + timedelta(days=1))),
        )
        _, (changed_agent,) = self._experience(tenant_id, config_y, ((config_y, t2 + timedelta(days=2)),))

        self._upgrade()
        self.assertEqual(self.connection.execute(text(
            "SELECT agent_id FROM tenant_voice_experiences WHERE id = :id"
        ), {"id": experience_a}).scalar_one(), agent_a)
        self.assertEqual(self.connection.execute(text(
            "SELECT id, agent_id, agent_version_id FROM tenant_voice_experience_versions ORDER BY published_at"
        )).all(), [(before, agent_a, a1), (between, agent_a, a1), (after, agent_a, a2),
                   (changed_agent, agent_b, b1)])
        self._downgrade()
        self._upgrade()
        self.assertEqual(self.connection.execute(text(
            "SELECT id, agent_version_id FROM tenant_voice_experience_versions ORDER BY published_at"
        )).all(), [(before, a1), (between, a1), (after, a2), (changed_agent, b1)])
        columns = {column["name"]: column for column in __import__("sqlalchemy").inspect(self.connection).get_columns(
            "tenant_voice_experience_versions", schema=self.schema
        )}
        self.assertFalse(columns["agent_id"]["nullable"])
        self.assertFalse(columns["agent_version_id"]["nullable"])

    def test_missing_ambiguous_draft_only_cross_tenant_and_tied_bindings_fail_closed(self) -> None:
        scenarios = ("missing", "ambiguous", "draft_only", "cross_tenant", "timestamp_tie")
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.connection.close()
                with self.engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
                    connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
                self._connect_schema()
                tenant, other_tenant, config = str(uuid4()), str(uuid4()), str(uuid4())
                when = datetime(2026, 1, 1, tzinfo=UTC)
                if scenario == "ambiguous":
                    self._agent(tenant, (("published", config, when),))
                    self._agent(tenant, (("published", config, when + timedelta(days=1)),))
                elif scenario == "draft_only":
                    self._agent(tenant, (("draft", config, None),))
                elif scenario == "cross_tenant":
                    self._agent(other_tenant, (("published", config, when),))
                    self.connection.execute(text(
                        "INSERT INTO tenant_agent_versions (id, agent_id, tenant_id, status, voice_agent_config_id, published_at) "
                        "SELECT :id, id, :tenant, 'published', :config, :published_at FROM tenant_agents WHERE tenant_id = :other"
                    ), {"id": str(uuid4()), "tenant": tenant, "config": config, "published_at": when,
                        "other": other_tenant})
                elif scenario == "timestamp_tie":
                    self._agent(tenant, (("published", config, when), ("superseded", config, when)))
                self._experience(tenant, config, ((config, when + timedelta(days=2)),))
                with self.assertRaises(RuntimeError):
                    self._upgrade()

    def test_draft_versions_are_not_used_for_legacy_binding_backfill(self) -> None:
        tenant, config = str(uuid4()), str(uuid4())
        self._agent(tenant, (("draft", config, None),))
        self._experience(tenant, config, ((config, datetime.now(UTC)),))
        with self.assertRaisesRegex(RuntimeError, "no published AgentVersion"):
            self._upgrade()


if __name__ == "__main__":
    unittest.main()
