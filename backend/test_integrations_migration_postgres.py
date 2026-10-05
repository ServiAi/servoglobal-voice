r"""Real PostgreSQL migration tests for 202610050001 (WhatsApp provider message identity).

Needs its own disposable database (the schema is rebuilt with Alembic from scratch):

    $env:INTEGRATIONS_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_integrations_migration_test"
    .\.venv\Scripts\python.exe -m unittest test_integrations_migration_postgres -v
"""

from __future__ import annotations

import os
import unittest
from uuid import uuid4

MIGRATION_TEST_DATABASE_URL = os.environ.get("INTEGRATIONS_MIGRATION_TEST_DATABASE_URL")
if MIGRATION_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ["DATABASE_URL"] = MIGRATION_TEST_DATABASE_URL

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

BEFORE = "202609240001"
AFTER = "202610050001"
UNIQUE_INDEX = "uq_crm_whatsapp_messages_tenant_provider_message"
OLD_INDEX = "ix_crm_whatsapp_messages_tenant_provider_message"


def _config() -> Config:
    return Config(os.path.join(os.path.dirname(os.path.abspath(__file__)), "alembic.ini"))


@unittest.skipUnless(
    MIGRATION_TEST_DATABASE_URL,
    "INTEGRATIONS_MIGRATION_TEST_DATABASE_URL not set; skipping real PostgreSQL migration tests",
)
class WhatsAppProviderMessageIntegrityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(MIGRATION_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("INTEGRATIONS_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        with cls.engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(_config(), BEFORE)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        # Every test starts from the pre-migration schema with no messages.
        if self._revision() != BEFORE:
            command.downgrade(_config(), BEFORE)
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM crm_whatsapp_messages"))
            conn.execute(text("DELETE FROM tenants"))

    # -- helpers ----------------------------------------------------------------------------------

    def _revision(self) -> str | None:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()

    def _indexes(self) -> dict[str, str]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'crm_whatsapp_messages'")
            )
            return {name: definition for name, definition in rows}

    def _tenant(self) -> str:
        tenant_id = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tenants (id, name, slug, timezone, status) VALUES (:id, 'T', :slug, 'UTC', 'active')"),
                {"id": tenant_id, "slug": f"mig-{uuid4().hex[:10]}"},
            )
        return tenant_id

    def _message(self, tenant_id: str, provider_message_id: str | None, direction: str = "outbound") -> str:
        message_id = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO crm_whatsapp_messages "
                    "(id, tenant_id, provider, direction, status, metadata_json, created_at, updated_at, provider_message_id) "
                    "VALUES (:id, :tenant, 'whatsapp_cloud', :direction, 'sent', '{}', now(), now(), :pmid)"
                ),
                {"id": message_id, "tenant": tenant_id, "direction": direction, "pmid": provider_message_id},
            )
        return message_id

    def _count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT count(*) FROM crm_whatsapp_messages")).scalar()

    # -- tests ------------------------------------------------------------------------------------

    def test_before_state_has_only_the_non_unique_index(self) -> None:
        indexes = self._indexes()
        self.assertIn(OLD_INDEX, indexes)
        self.assertNotIn("UNIQUE", indexes[OLD_INDEX])
        self.assertNotIn(UNIQUE_INDEX, indexes)

    def test_upgrade_replaces_the_index_with_a_partial_unique_one_and_keeps_rows(self) -> None:
        tenant_a, tenant_b = self._tenant(), self._tenant()
        self._message(tenant_a, "wamid.X")
        self._message(tenant_b, "wamid.X")  # same id, other tenant
        self._message(tenant_a, None)
        self._message(tenant_a, None)  # NULLs repeat
        rows_before = self._count()

        command.upgrade(_config(), AFTER)

        indexes = self._indexes()
        self.assertEqual(self._revision(), AFTER)
        self.assertNotIn(OLD_INDEX, indexes)
        definition = indexes[UNIQUE_INDEX]
        self.assertIn("UNIQUE", definition)
        self.assertIn("(tenant_id, provider_message_id)", definition)
        self.assertIn("provider_message_id IS NOT NULL", definition)
        self.assertEqual(self._count(), rows_before)
        with self.engine.connect() as conn:
            valid = conn.execute(
                text("SELECT indisvalid FROM pg_index WHERE indexrelid = CAST(:name AS regclass)"), {"name": UNIQUE_INDEX}
            ).scalar()
        self.assertTrue(valid)

        # The invariant now lives in the database: a writer that bypasses the service cannot duplicate.
        with self.assertRaises(IntegrityError):
            self._message(tenant_a, "wamid.X", direction="inbound")
        self._message(self._tenant(), "wamid.X")  # another tenant is still fine
        self._message(tenant_a, None)  # and so is another NULL

    def test_upgrade_aborts_on_existing_duplicates_without_touching_data(self) -> None:
        tenant = self._tenant()
        first = self._message(tenant, "wamid.123")
        second = self._message(tenant, "wamid.123", direction="inbound")

        with self.assertRaises(Exception) as raised:
            command.upgrade(_config(), AFTER)

        self.assertIn("1 duplicate", str(raised.exception))
        self.assertIn("audit_whatsapp_message_duplicates", str(raised.exception))
        self.assertEqual(self._revision(), BEFORE)
        self.assertEqual(self._count(), 2)
        with self.engine.connect() as conn:
            ids = {row[0] for row in conn.execute(text("SELECT id FROM crm_whatsapp_messages"))}
        self.assertEqual(ids, {first, second})
        indexes = self._indexes()
        self.assertIn(OLD_INDEX, indexes)
        self.assertNotIn(UNIQUE_INDEX, indexes)

    def test_downgrade_restores_the_original_index_without_losing_rows(self) -> None:
        tenant = self._tenant()
        self._message(tenant, "wamid.keep")
        self._message(tenant, None)
        command.upgrade(_config(), AFTER)

        command.downgrade(_config(), BEFORE)

        indexes = self._indexes()
        self.assertEqual(self._revision(), BEFORE)
        self.assertIn(OLD_INDEX, indexes)
        self.assertNotIn("UNIQUE", indexes[OLD_INDEX])
        self.assertNotIn(UNIQUE_INDEX, indexes)
        self.assertEqual(self._count(), 2)
        self._message(tenant, "wamid.keep")  # duplicates are possible again after downgrade

    def test_upgrade_downgrade_upgrade_cycle(self) -> None:
        self._message(self._tenant(), "wamid.cycle")
        command.upgrade(_config(), AFTER)
        command.downgrade(_config(), BEFORE)
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM crm_whatsapp_messages"))  # downgrade allowed a duplicate-free state
        command.upgrade(_config(), AFTER)
        self.assertEqual(self._revision(), AFTER)
        self.assertIn(UNIQUE_INDEX, self._indexes())

    def test_there_is_a_single_alembic_head_and_metadata_matches_the_migration(self) -> None:
        self.assertEqual(ScriptDirectory.from_config(_config()).get_heads(), [AFTER])

        import app.models  # noqa: F401  (registers every model)
        from app.db.base import Base

        table = Base.metadata.tables["crm_whatsapp_messages"]
        indexes = {index.name: index for index in table.indexes}
        self.assertIn(UNIQUE_INDEX, indexes)
        self.assertTrue(indexes[UNIQUE_INDEX].unique)
        self.assertEqual([c.name for c in indexes[UNIQUE_INDEX].columns], ["tenant_id", "provider_message_id"])
        self.assertNotIn(OLD_INDEX, indexes)
        where = indexes[UNIQUE_INDEX].dialect_options["postgresql"]["where"]
        self.assertEqual(str(where), "provider_message_id IS NOT NULL")


if __name__ == "__main__":
    unittest.main()
