"""PostgreSQL migration gate for the public WebRTC canonical runtime revision.

Run only with a disposable database:
    $env:PUBLIC_WEBRTC_MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://.../public_webrtc_migration_test"
    python -m unittest test_public_webrtc_migration_postgres -v
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

DATABASE_URL = os.environ.get("PUBLIC_WEBRTC_MIGRATION_TEST_DATABASE_URL")
MIGRATION_PATH = Path(__file__).parent / "alembic" / "versions" / "202610100001_public_webrtc_canonical_runtime.py"


@unittest.skipUnless(
    DATABASE_URL,
    "PUBLIC_WEBRTC_MIGRATION_TEST_DATABASE_URL not set; skipping PostgreSQL migration tests",
)
class PublicWebRTCCanonicalRuntimeMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("PUBLIC_WEBRTC_MIGRATION_TEST_DATABASE_URL must point to PostgreSQL")
        spec = importlib.util.spec_from_file_location("public_webrtc_migration", MIGRATION_PATH)
        assert spec and spec.loader
        cls.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.migration)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.schema = "wr135_" + uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql(f'SET search_path TO "{self.schema}"')
        self.connection.commit()
        metadata = MetaData()
        Table("voice_sessions", metadata, Column("id", String(36), primary_key=True))
        Table(
            "tenant_voice_runtime_calls", metadata,
            Column("id", String(36), primary_key=True), Column("status", String(16), nullable=False),
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

    def _legacy_row(self, status: str = "starting") -> str:
        """A row as it exists BEFORE the migration (no launch_runtime column yet)."""
        row_id = str(uuid4())
        self.connection.execute(
            text("INSERT INTO tenant_voice_runtime_calls (id, status) VALUES (:id, :status)"),
            {"id": row_id, "status": status},
        )
        return row_id

    def _runtime(self, voice_session_id: str | None = None, launch_runtime: str = "canonical_voice_session") -> str:
        """A row inserted AFTER the migration."""
        row_id = str(uuid4())
        self.connection.execute(
            text(
                "INSERT INTO tenant_voice_runtime_calls (id, status, launch_runtime, voice_session_id) "
                "VALUES (:id, 'ready', :runtime, :vs)"
            ),
            {"id": row_id, "runtime": launch_runtime, "vs": voice_session_id},
        )
        return row_id

    def _session(self) -> str:
        session_id = str(uuid4())
        self.connection.execute(text("INSERT INTO voice_sessions (id) VALUES (:id)"), {"id": session_id})
        return session_id

    def test_legacy_rows_stay_null_and_canonical_rows_correlate(self) -> None:
        legacy = [self._legacy_row(status) for status in ("starting", "reserved", "ready", "ended", "unknown")]
        self.connection.commit()
        self._run(self.migration.upgrade)

        rows = self.connection.execute(
            text("SELECT launch_runtime, voice_session_id FROM tenant_voice_runtime_calls WHERE id = ANY(:ids)"),
            {"ids": legacy},
        ).all()
        self.assertEqual(rows, [("legacy_provider", None)] * len(legacy))  # every pre-existing row is legacy
        columns = {c["name"]: c for c in inspect(self.connection).get_columns("tenant_voice_runtime_calls", schema=self.schema)}
        self.assertTrue(columns["voice_session_id"]["nullable"])
        self.assertFalse(columns["launch_runtime"]["nullable"])
        session_id = self._session()
        canonical = self._runtime(session_id)
        self.assertEqual(self.connection.execute(
            text("SELECT voice_session_id FROM tenant_voice_runtime_calls WHERE id = :id"), {"id": canonical}
        ).scalar_one(), session_id)
        self.assertEqual(self.connection.execute(
            text("SELECT launch_runtime FROM tenant_voice_runtime_calls WHERE id = :id"), {"id": canonical}
        ).scalar_one(), "canonical_voice_session")
        self.connection.commit()

    def test_launch_runtime_only_accepts_the_two_known_modes(self) -> None:
        self._run(self.migration.upgrade)
        self._runtime(launch_runtime="legacy_provider")
        self._runtime(launch_runtime="canonical_voice_session")
        self.connection.commit()
        with self.assertRaises(IntegrityError):
            self._runtime(launch_runtime="foo")
        self.connection.rollback()
        with self.assertRaises(IntegrityError):  # NOT NULL after the backfill
            self.connection.execute(text("INSERT INTO tenant_voice_runtime_calls (id, status) VALUES (:id, 'ready')"), {"id": str(uuid4())})
        self.connection.rollback()

    def test_one_session_belongs_to_one_ledger_row_and_the_fk_is_enforced(self) -> None:
        self._run(self.migration.upgrade)
        session_id = self._session()
        self._runtime(session_id)
        self._runtime()  # any number of NULL rows is fine (partial unique)
        self._runtime()
        self.connection.commit()

        with self.assertRaises(IntegrityError):
            self._runtime(session_id)
        self.connection.rollback()
        with self.assertRaises(IntegrityError):
            self._runtime(str(uuid4()))
        self.connection.rollback()
        with self.assertRaises(IntegrityError):  # ON DELETE RESTRICT keeps the correlation
            self.connection.execute(text("DELETE FROM voice_sessions WHERE id = :id"), {"id": session_id})
        self.connection.rollback()

    def test_downgrade_and_reupgrade(self) -> None:
        self._run(self.migration.upgrade)
        self._run(self.migration.downgrade)
        names = {c["name"] for c in inspect(self.connection).get_columns("tenant_voice_runtime_calls", schema=self.schema)}
        self.assertNotIn("voice_session_id", names)
        self.assertNotIn("launch_runtime", names)
        self._run(self.migration.upgrade)
        indexes = {i["name"] for i in inspect(self.connection).get_indexes("tenant_voice_runtime_calls", schema=self.schema)}
        self.assertIn("uq_voice_runtime_voice_session", indexes)


if __name__ == "__main__":
    unittest.main()
