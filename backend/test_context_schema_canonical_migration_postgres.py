"""PostgreSQL migration gate for 202610110001 (Context Schema canonical control plane).

Run only with a disposable database:
    $env:CONTEXT_SCHEMA_CANONICAL_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://.../context_schema_migration_test"
    python -m unittest test_context_schema_canonical_migration_postgres -v
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.environ.get("CONTEXT_SCHEMA_CANONICAL_MIGRATION_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parent / "alembic" / "versions" / "202610110001_canonical_context_schema_control_plane.py"

LEGACY_DDL = (
    "CREATE TABLE tenant_agents (id varchar(36) PRIMARY KEY, tenant_id varchar(36) NOT NULL)",
    "CREATE TABLE tenant_agent_versions (id varchar(36) PRIMARY KEY, agent_id varchar(36) NOT NULL REFERENCES tenant_agents(id),"
    " tenant_id varchar(36) NOT NULL, voice_agent_config_id varchar(36))",
    "CREATE TABLE tenant_voice_context_schemas (id varchar(36) PRIMARY KEY, tenant_id varchar(36) NOT NULL,"
    " agent_config_id varchar(36) NOT NULL, schema_key varchar(80) NOT NULL, version integer NOT NULL DEFAULT 1,"
    " status varchar(16) NOT NULL,"
    " CONSTRAINT uq_tenant_voice_context_schemas_lineage_version UNIQUE (tenant_id, agent_config_id, schema_key, version))",
    "CREATE INDEX ix_tenant_voice_context_schemas_tenant_agent ON tenant_voice_context_schemas (tenant_id, agent_config_id)",
    "CREATE UNIQUE INDEX uq_tenant_voice_context_schemas_active_lineage ON tenant_voice_context_schemas"
    " (tenant_id, agent_config_id, schema_key) WHERE status = 'active'",
    "CREATE UNIQUE INDEX uq_tenant_voice_context_schemas_draft_lineage ON tenant_voice_context_schemas"
    " (tenant_id, agent_config_id, schema_key) WHERE status = 'draft'",
    "CREATE TABLE tenant_voice_experiences (id varchar(36) PRIMARY KEY, tenant_id varchar(36) NOT NULL,"
    " agent_config_id varchar(36) NOT NULL, agent_id varchar(36) NOT NULL REFERENCES tenant_agents(id),"
    " context_schema_id varchar(36) NOT NULL REFERENCES tenant_voice_context_schemas(id))",
    "CREATE INDEX ix_tenant_voice_experiences_tenant_agent ON tenant_voice_experiences (tenant_id, agent_config_id)",
    "CREATE TABLE tenant_voice_experience_versions (id varchar(36) PRIMARY KEY, tenant_id varchar(36) NOT NULL,"
    " experience_id varchar(36) NOT NULL REFERENCES tenant_voice_experiences(id), agent_config_id varchar(36) NOT NULL,"
    " agent_id varchar(36) NOT NULL REFERENCES tenant_agents(id), agent_version_id varchar(36) NOT NULL REFERENCES tenant_agent_versions(id),"
    " context_schema_id varchar(36) NOT NULL REFERENCES tenant_voice_context_schemas(id))",
    "CREATE TABLE tenant_voice_runtime_calls (id varchar(36) PRIMARY KEY, agent_config_id varchar(36) NOT NULL)",
)


@unittest.skipUnless(
    DATABASE_URL,
    "CONTEXT_SCHEMA_CANONICAL_MIGRATION_TEST_DATABASE_URL not set; skipping PostgreSQL migration tests",
)
class ContextSchemaCanonicalMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("CONTEXT_SCHEMA_CANONICAL_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        spec = importlib.util.spec_from_file_location("context_schema_canonical_migration", MIGRATION_PATH)
        assert spec and spec.loader
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.schema = "cs138_" + uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql(f'SET search_path TO "{self.schema}"')
        self.connection.commit()
        for statement in LEGACY_DDL:
            self.connection.exec_driver_sql(statement)
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        with self.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))

    # -- fixtures ------------------------------------------------------------------------------------

    def _upgrade(self) -> None:
        if self.connection.in_transaction():
            self.connection.commit()
        with self.connection.begin():
            with Operations.context(MigrationContext.configure(self.connection)):
                self.migration.upgrade()

    def _agent(self, tenant: str, config: str | None) -> str:
        agent_id = str(uuid4())
        self.connection.execute(text("INSERT INTO tenant_agents VALUES (:id, :tenant)"), {"id": agent_id, "tenant": tenant})
        self.connection.execute(
            text("INSERT INTO tenant_agent_versions VALUES (:id, :agent, :tenant, :config)"),
            {"id": str(uuid4()), "agent": agent_id, "tenant": tenant, "config": config},
        )
        return agent_id

    def _schema(self, tenant: str, config: str, key: str = "intake", version: int = 1, status: str = "active") -> str:
        schema_id = str(uuid4())
        self.connection.execute(
            text("INSERT INTO tenant_voice_context_schemas VALUES (:id, :tenant, :config, :key, :version, :status)"),
            {"id": schema_id, "tenant": tenant, "config": config, "key": key, "version": version, "status": status},
        )
        return schema_id

    def _experience(self, tenant: str, config: str, agent_id: str, schema_id: str) -> str:
        experience_id = str(uuid4())
        self.connection.execute(
            text("INSERT INTO tenant_voice_experiences VALUES (:id, :tenant, :config, :agent, :schema)"),
            {"id": experience_id, "tenant": tenant, "config": config, "agent": agent_id, "schema": schema_id},
        )
        return experience_id

    def _published_version(self, tenant: str, config: str, experience_id: str, agent_id: str, schema_id: str) -> tuple[str, str]:
        agent_version_id = self.connection.execute(
            text("SELECT id FROM tenant_agent_versions WHERE agent_id = :agent"), {"agent": agent_id}
        ).scalar_one()
        version_id = str(uuid4())
        self.connection.execute(
            text("INSERT INTO tenant_voice_experience_versions VALUES (:id, :tenant, :exp, :config, :agent, :av, :schema)"),
            {"id": version_id, "tenant": tenant, "exp": experience_id, "config": config, "agent": agent_id,
             "av": agent_version_id, "schema": schema_id},
        )
        return version_id, agent_version_id

    def _columns(self, table: str) -> dict[str, dict]:
        return {column["name"]: column for column in inspect(self.connection).get_columns(table, schema=self.schema)}

    def _assert_untouched(self) -> None:
        """A failed migration rolls back completely: legacy shape, no half-applied canonical column."""
        self.connection.rollback()
        self.assertIn("agent_config_id", self._columns("tenant_voice_context_schemas"))
        self.assertNotIn("agent_id", self._columns("tenant_voice_context_schemas"))
        self.assertIn("agent_config_id", self._columns("tenant_voice_experiences"))

    # -- tests ---------------------------------------------------------------------------------------

    def test_upgrade_backfills_the_canonical_agent_and_preserves_published_history(self) -> None:
        tenant, config_a, config_b = (str(uuid4()) for _ in range(3))
        agent_a, agent_b = self._agent(tenant, config_a), self._agent(tenant, config_b)
        v1 = self._schema(tenant, config_a, version=1, status="archived")
        v2 = self._schema(tenant, config_a, version=2, status="active")
        draft = self._schema(tenant, config_a, version=3, status="draft")
        other = self._schema(tenant, config_b, key="other")
        experience = self._experience(tenant, config_a, agent_a, v1)
        published, agent_version = self._published_version(tenant, config_a, experience, agent_a, v1)
        self.connection.execute(text("INSERT INTO tenant_voice_runtime_calls VALUES ('r1', :config)"), {"config": config_a})

        self._upgrade()

        rows = dict(self.connection.execute(text("SELECT id, agent_id FROM tenant_voice_context_schemas")).all())
        self.assertEqual(rows, {v1: agent_a, v2: agent_a, draft: agent_a, other: agent_b})
        # published history: the exact AgentVersion and the exact (now archived) schema row are untouched
        self.assertEqual(
            self.connection.execute(
                text("SELECT agent_id, agent_version_id, context_schema_id FROM tenant_voice_experience_versions WHERE id = :id"),
                {"id": published},
            ).one(),
            (agent_a, agent_version, v1),
        )
        for table in ("tenant_voice_context_schemas", "tenant_voice_experiences", "tenant_voice_experience_versions"):
            self.assertNotIn("agent_config_id", self._columns(table), table)
        schemas = self._columns("tenant_voice_context_schemas")
        self.assertFalse(schemas["agent_id"]["nullable"])
        runtime = self._columns("tenant_voice_runtime_calls")
        self.assertTrue(runtime["agent_config_id"]["nullable"])  # historical evidence, kept
        self.assertEqual(
            self.connection.execute(text("SELECT agent_config_id FROM tenant_voice_runtime_calls")).scalar_one(), config_a
        )
        foreign_keys = inspect(self.connection).get_foreign_keys("tenant_voice_context_schemas", schema=self.schema)
        self.assertEqual({(fk["referred_table"], fk["options"].get("ondelete")) for fk in foreign_keys}, {("tenant_agents", "CASCADE")})

    def test_lineage_keys_are_rebuilt_on_the_agent(self) -> None:
        tenant, config = str(uuid4()), str(uuid4())
        agent = self._agent(tenant, config)
        self._schema(tenant, config, status="archived")
        self._upgrade()

        def insert(version: int, status: str) -> None:
            with self.connection.begin_nested():
                self.connection.execute(
                    text("INSERT INTO tenant_voice_context_schemas (id, tenant_id, schema_key, version, status, agent_id)"
                         " VALUES (:id, :tenant, 'intake', :version, :status, :agent)"),
                    {"id": str(uuid4()), "tenant": tenant, "version": version, "status": status, "agent": agent},
                )

        insert(2, "active")
        insert(3, "draft")
        for version, status in ((4, "active"), (5, "draft"), (1, "archived")):  # second active/draft, repeated version
            with self.assertRaises(IntegrityError):
                insert(version, status)

    def test_a_schema_without_a_canonical_agent_aborts_and_leaves_the_legacy_shape(self) -> None:
        tenant = str(uuid4())
        self._schema(tenant, str(uuid4()))
        with self.assertRaisesRegex(RuntimeError, "no canonical Agent"):
            self._upgrade()
        self._assert_untouched()

    def test_a_legacy_config_shared_by_two_agents_is_ambiguous_and_aborts(self) -> None:
        tenant, config = str(uuid4()), str(uuid4())
        self._agent(tenant, config)
        self._agent(tenant, config)
        self._schema(tenant, config)
        with self.assertRaisesRegex(RuntimeError, "more than one Agent"):
            self._upgrade()
        self._assert_untouched()

    def test_an_agent_of_another_tenant_does_not_satisfy_the_binding(self) -> None:
        tenant, other_tenant, config = str(uuid4()), str(uuid4()), str(uuid4())
        self._agent(other_tenant, config)
        self._schema(tenant, config)
        with self.assertRaisesRegex(RuntimeError, "no canonical Agent"):
            self._upgrade()
        self._assert_untouched()

    def test_a_version_whose_agent_belongs_to_another_tenant_aborts(self) -> None:
        tenant, other_tenant, config = str(uuid4()), str(uuid4()), str(uuid4())
        agent = self._agent(other_tenant, config)
        self.connection.execute(
            text("INSERT INTO tenant_agent_versions VALUES (:id, :agent, :tenant, :config)"),
            {"id": str(uuid4()), "agent": agent, "tenant": tenant, "config": config},
        )
        self._schema(tenant, config)
        with self.assertRaisesRegex(RuntimeError, "tenant does not match"):
            self._upgrade()
        self._assert_untouched()

    def test_schema_referenced_across_tenants_aborts(self) -> None:
        tenant_a, tenant_b, config_a, config_b = (str(uuid4()) for _ in range(4))
        agent_a, agent_b = self._agent(tenant_a, config_a), self._agent(tenant_b, config_b)
        schema = self._schema(tenant_a, config_a)
        self._experience(tenant_b, config_b, agent_b, schema)  # tenant B's experience points at tenant A's schema
        with self.assertRaisesRegex(RuntimeError, "across tenants"):
            self._upgrade()
        self._assert_untouched()
        self.assertTrue(agent_a)

    def test_an_experience_whose_agent_disagrees_with_the_schema_aborts(self) -> None:
        tenant, config_a, config_b = (str(uuid4()) for _ in range(3))
        self._agent(tenant, config_a)
        agent_b = self._agent(tenant, config_b)
        schema = self._schema(tenant, config_a)
        self._experience(tenant, config_a, agent_b, schema)
        with self.assertRaisesRegex(RuntimeError, "disagrees"):
            self._upgrade()
        self._assert_untouched()

    def test_errors_never_leak_business_data(self) -> None:
        tenant = str(uuid4())
        self._schema(tenant, str(uuid4()), key="pii_phone_573001112233")
        with self.assertRaises(RuntimeError) as raised:
            self._upgrade()
        self.assertNotIn("573001112233", str(raised.exception))
        self.assertNotIn("pii_phone", str(raised.exception))

    def test_downgrade_is_blocked_explicitly(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not reversible"):
            self.migration.downgrade()


if __name__ == "__main__":
    unittest.main()
