"""PostgreSQL migration gate for the CRM voice call ``origin`` revision.

    $env:CRM_CALL_ORIGIN_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://.../crm_call_origin_migration_test"
    python -m unittest test_crm_voice_call_origin_migration_postgres -v
"""

from __future__ import annotations

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

DATABASE_URL = os.environ.get("CRM_CALL_ORIGIN_MIGRATION_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parent / "alembic" / "versions" / "202610100002_crm_voice_call_origin.py"


@unittest.skipUnless(DATABASE_URL, "CRM_CALL_ORIGIN_MIGRATION_TEST_DATABASE_URL not set; skipping PostgreSQL migration tests")
class CrmVoiceCallOriginMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("CRM_CALL_ORIGIN_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        spec = importlib.util.spec_from_file_location("crm_call_origin_migration", MIGRATION_PATH)
        assert spec and spec.loader
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.schema = "co136_" + uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql(f'SET search_path TO "{self.schema}"')
        self.connection.commit()
        metadata = MetaData()
        Table(
            "crm_voice_calls", metadata,
            Column("id", String(36), primary_key=True), Column("provider", String(40), nullable=False),
            Column("source_submission_id", String(36), nullable=True), Column("status", String(32), nullable=False),
        )
        metadata.create_all(self.connection)
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()
        with self.engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))

    def _run(self, step) -> None:
        if self.connection.in_transaction():
            self.connection.commit()
        with self.connection.begin():
            with Operations.context(MigrationContext.configure(self.connection)):
                step()

    def _insert(self, provider: str, submission: str | None, **extra) -> str:
        row_id = str(uuid4())
        columns = "id, provider, source_submission_id, status" + "".join(f", {key}" for key in extra)
        values = ":id, :provider, :sub, 'requested'" + "".join(f", :{key}" for key in extra)
        self.connection.execute(
            text(f"INSERT INTO crm_voice_calls ({columns}) VALUES ({values})"),
            {"id": row_id, "provider": provider, "sub": submission, **extra},
        )
        return row_id

    def _origins(self) -> dict[str, str]:
        return dict(self.connection.execute(text("SELECT id, origin FROM crm_voice_calls")).all())

    def test_backfill_classifies_only_provable_callbacks_and_defaults_the_rest_to_crm(self) -> None:
        legacy_callback = self._insert("ultravox", str(uuid4()))
        canonical_callback = self._insert("livekit_sip", str(uuid4()))
        crm_sip = self._insert("livekit_sip", None)
        crm_other = self._insert("ultravox", None)
        self.connection.commit()

        self._run(self.migration.upgrade)

        origins = self._origins()
        self.assertEqual(origins[legacy_callback], "legacy_voice_experience_callback")
        self.assertEqual(origins[canonical_callback], "voice_experience_callback")
        self.assertEqual(origins[crm_sip], "crm_outbound")
        self.assertEqual(origins[crm_other], "crm_outbound")

    def test_an_old_writer_without_origin_is_never_a_voice_experience_callback(self) -> None:
        self._run(self.migration.upgrade)
        old_writer = self._insert("ultravox", str(uuid4()))  # a pre-origin replica creating a callback
        explicit = self._insert("livekit_sip", str(uuid4()), origin="voice_experience_callback")
        self.connection.commit()

        origins = self._origins()
        self.assertEqual(origins[old_writer], "crm_outbound")
        self.assertEqual(origins[explicit], "voice_experience_callback")
        column = {c["name"]: c for c in inspect(self.connection).get_columns("crm_voice_calls", schema=self.schema)}["origin"]
        self.assertFalse(column["nullable"])
        self.assertIn("crm_outbound", column["default"])

    def test_only_the_known_origins_are_accepted(self) -> None:
        self._run(self.migration.upgrade)
        with self.assertRaises(IntegrityError):
            self._insert("livekit_sip", None, origin="foo")
        self.connection.rollback()
        with self.assertRaises(IntegrityError):
            self.connection.execute(
                text("INSERT INTO crm_voice_calls (id, provider, status, origin) VALUES (:id, 'x', 'requested', NULL)"),
                {"id": str(uuid4())},
            )
        self.connection.rollback()

    def test_downgrade_and_reupgrade(self) -> None:
        self._insert("livekit_sip", str(uuid4()))
        self.connection.commit()
        self._run(self.migration.upgrade)
        self._run(self.migration.downgrade)
        names = {c["name"] for c in inspect(self.connection).get_columns("crm_voice_calls", schema=self.schema)}
        self.assertNotIn("origin", names)
        self._run(self.migration.upgrade)
        self.assertEqual(set(self._origins().values()), {"voice_experience_callback"})


if __name__ == "__main__":
    unittest.main()
