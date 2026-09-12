from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION = Path(__file__).parent / "alembic" / "versions" / "202609120001_agent_delete_preserve_voice_sessions.py"


class AgentDeleteMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_sessions_and_adds_nullable_set_null_references(self) -> None:
        spec = importlib.util.spec_from_file_location("agent_delete_migration", MIGRATION)
        assert spec and spec.loader
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        engine = sa.create_engine("sqlite:///:memory:")
        metadata = sa.MetaData()
        sa.Table("tenant_agents", metadata, sa.Column("id", sa.String(36), primary_key=True))
        sa.Table("tenant_agent_versions", metadata, sa.Column("id", sa.String(36), primary_key=True))
        sa.Table(
            "voice_sessions", metadata,
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("agent_id", sa.String(36), sa.ForeignKey("tenant_agents.id"), nullable=False),
            sa.Column("agent_version_id", sa.String(36), sa.ForeignKey("tenant_agent_versions.id"), nullable=False),
        )
        with engine.begin() as connection:
            metadata.create_all(connection)
            connection.execute(sa.text("INSERT INTO tenant_agents (id) VALUES ('agent-1')"))
            connection.execute(sa.text("INSERT INTO tenant_agent_versions (id) VALUES ('version-1')"))
            connection.execute(sa.text("INSERT INTO voice_sessions (id, agent_id, agent_version_id) VALUES ('session-1', 'agent-1', 'version-1')"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            columns = {column["name"]: column for column in sa.inspect(connection).get_columns("voice_sessions")}
            self.assertTrue(columns["agent_id"]["nullable"])
            self.assertTrue(columns["agent_version_id"]["nullable"])
            self.assertIn("deleted_agent_id", columns)
            self.assertIn("deleted_agent_version_id", columns)
            foreign_keys = {tuple(fk["constrained_columns"]): fk for fk in sa.inspect(connection).get_foreign_keys("voice_sessions")}
            self.assertEqual(foreign_keys[("agent_id",)]["options"].get("ondelete"), "SET NULL")
            self.assertEqual(foreign_keys[("agent_version_id",)]["options"].get("ondelete"), "SET NULL")
            self.assertEqual(connection.scalar(sa.text("SELECT agent_id FROM voice_sessions WHERE id='session-1'")), "agent-1")
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
            columns = {column["name"]: column for column in sa.inspect(connection).get_columns("voice_sessions")}
            self.assertFalse(columns["agent_id"]["nullable"])
            self.assertFalse(columns["agent_version_id"]["nullable"])
            self.assertNotIn("deleted_agent_id", columns)


if __name__ == "__main__":
    unittest.main()
