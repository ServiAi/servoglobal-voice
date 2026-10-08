from __future__ import annotations

import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.agents.public import (
    AgentRuntimeTarget,
    AgentRuntimeTargetUnavailableError,
    AgentsFacade,
)
from app.modules.voice.application.session_service import VoiceSessionError, VoiceSessionService
from app.modules.voice.public import VoiceSessionFacade, VoiceSessionRef

REALTIME = {"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "ultravox"}}


class ExactAgentVersionRuntimeTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other_tenant, _ = self._seed_tenant_user(slug="tenant-b", email="b@example.com")

    def _agent(self, *, tenant_id: str | None = None, statuses=("superseded", "published"), agent_status="active",
               runtime=REALTIME) -> tuple[str, list[str]]:
        """Agent with one version per status, in order; the last 'published' one is the pointer."""
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id or self.tenant.id, name="Sandra", status="draft")
            db.add(agent)
            db.flush()
            ids = []
            for number, status in enumerate(statuses, start=1):
                version = TenantAgentVersion(
                    tenant_id=agent.tenant_id, agent_id=agent.id, version=number, status=status,
                    language="es-CO", timezone="America/Bogota", identity_json={"name": "Sandra"},
                    instructions_json={"system_prompt": f"Prompt v{number}", "greeting": "Hola"},
                    behavior_json={}, runtime_binding_json=runtime,
                )
                db.add(version)
                db.flush()
                ids.append(version.id)
                if status == "published":
                    agent.published_version_id = version.id
            agent.status = agent_status
            db.commit()
            return agent.id, ids

    def _create_exact(self, agent_id, version_id, **kwargs):
        kwargs.setdefault("channel", "internal_test")
        kwargs.setdefault("direction", "internal")
        with SessionLocal() as db:
            return VoiceSessionFacade(db).create_session_from_agent_version(
                self.tenant.id, agent_id, version_id, **kwargs
            )

    def test_superseded_and_published_versions_are_executable_and_pinned_exactly(self) -> None:
        agent_id, (superseded, published) = self._agent()
        old = self._create_exact(agent_id, superseded)
        current = self._create_exact(agent_id, published)
        self.assertEqual((old.agent_version_id, current.agent_version_id), (superseded, published))
        with SessionLocal() as db:
            legacy = VoiceSessionService(db).create(self.tenant.id, agent_id, channel="internal_test", direction="internal")
            self.assertEqual(legacy.agent_version_id, published)  # create() is unchanged: current published

    def test_draft_version_archived_agent_and_other_tenants_are_not_executable(self) -> None:
        agent_id, (published, draft) = self._agent(statuses=("published", "draft"))
        with self.assertRaisesRegex(VoiceSessionError, "agent_version_not_executable"):
            self._create_exact(agent_id, draft)
        archived_id, (version,) = self._agent(statuses=("published",), agent_status="archived")
        with self.assertRaisesRegex(VoiceSessionError, "agent_archived"):
            self._create_exact(archived_id, version)
        other_agent, (_, other_version) = self._agent(tenant_id=self.other_tenant.id)
        for agent, version in ((other_agent, other_version), (agent_id, other_version), (other_agent, published)):
            with self.assertRaisesRegex(VoiceSessionError, "agent_version_not_found"):
                self._create_exact(agent, version)
        with self.assertRaisesRegex(VoiceSessionError, "agent_version_not_found"):
            self._create_exact(agent_id, "00000000-0000-0000-0000-000000000000")

    def test_inactive_agent_blocks_every_version_including_superseded(self) -> None:
        agent_id, (superseded, published) = self._agent(agent_status="draft")
        for version in (superseded, published):
            with self.assertRaisesRegex(VoiceSessionError, "^agent_not_active$"):
                self._create_exact(agent_id, version)
        with SessionLocal() as db, self.assertRaises(AgentRuntimeTargetUnavailableError) as raised:
            AgentsFacade(db).resolve_runtime_target(self.tenant.id, agent_id, superseded)
        self.assertEqual(raised.exception.code, "agent_not_active")

    def test_non_realtime_version_is_rejected(self) -> None:
        agent_id, (version,) = self._agent(statuses=("published",), runtime={"pipeline_type": "cascade"})
        with self.assertRaisesRegex(VoiceSessionError, "not configured for realtime"):
            self._create_exact(agent_id, version)

    def test_exact_path_builds_the_same_session_as_create(self) -> None:
        agent_id, (_, published) = self._agent()
        with SessionLocal() as db:
            service = VoiceSessionService(db)
            legacy = service.create(self.tenant.id, agent_id, channel="webrtc", direction="internal", purpose="qa")
            exact = service.create_from_agent_version(
                self.tenant.id, agent_id, published, channel="webrtc", direction="internal", purpose="qa"
            )
            self.assertNotEqual(legacy.id, exact.id)
            for field in ("tenant_id", "agent_id", "agent_version_id", "channel", "direction", "purpose",
                          "runtime_engine", "pipeline_type", "provider", "status", "session_context_json"):
                self.assertEqual(getattr(legacy, field), getattr(exact, field), field)
            self.assertEqual({e.event_type for e in legacy.events}, {e.event_type for e in exact.events})

    def test_idempotency_replays_and_never_crosses_versions(self) -> None:
        agent_id, (superseded, published) = self._agent()
        first = self._create_exact(agent_id, superseded, idempotency_key="k1")
        again = self._create_exact(agent_id, superseded, idempotency_key="k1")
        self.assertEqual(first.session_id, again.session_id)
        with self.assertRaisesRegex(VoiceSessionError, "idempotency_key_agent_version_conflict"):
            self._create_exact(agent_id, published, idempotency_key="k1")

    def test_session_ref_is_frozen_and_not_an_orm_row(self) -> None:
        agent_id, (_, published) = self._agent()
        ref = self._create_exact(agent_id, published)
        self.assertIsInstance(ref, VoiceSessionRef)
        self.assertEqual((ref.tenant_id, ref.agent_id, ref.status, ref.pipeline_type, ref.provider),
                         (self.tenant.id, agent_id, "requested", "realtime", "ultravox"))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.agent_version_id = "other"  # type: ignore[misc]

    def test_runtime_target_is_a_frozen_provider_agnostic_dto(self) -> None:
        agent_id, (superseded, published) = self._agent()
        with SessionLocal() as db:
            target = AgentsFacade(db).resolve_runtime_target(self.tenant.id, agent_id, superseded)
        self.assertIsInstance(target, AgentRuntimeTarget)
        self.assertEqual((target.version, target.version_status, target.is_realtime), (1, "superseded", True))
        self.assertEqual({f.name for f in dataclasses.fields(target)}, {
            "tenant_id", "agent_id", "agent_version_id", "version", "version_status", "pipeline_type",
            "realtime_provider"})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            target.agent_version_id = "x"  # type: ignore[misc]
        with SessionLocal() as db, self.assertRaises(AgentRuntimeTargetUnavailableError) as raised:
            AgentsFacade(db).resolve_runtime_target(self.other_tenant.id, agent_id, superseded)
        self.assertEqual(raised.exception.code, "agent_version_not_found")

    def test_no_version_drift_between_creation_and_runtime_spec_compilation(self) -> None:
        agent_id, (v1, v2) = self._agent()
        ref = self._create_exact(agent_id, v1)
        with SessionLocal() as db:  # the pointer moves on after the session exists
            agent = db.get(TenantAgent, agent_id)
            v3 = TenantAgentVersion(
                tenant_id=agent.tenant_id, agent_id=agent_id, version=3, status="published", language="es-CO",
                timezone="America/Bogota", identity_json={"name": "Sandra"},
                instructions_json={"system_prompt": "Prompt v3", "greeting": "Hola"}, behavior_json={},
                runtime_binding_json=REALTIME,
            )
            db.add(v3)
            db.flush()
            db.get(TenantAgentVersion, v2).status = "superseded"
            agent.published_version_id = v3.id
            db.commit()
            v3_id = v3.id
        with SessionLocal() as db:
            session = VoiceSessionService(db).get(ref.session_id)
            spec = AgentsFacade(db).compile_runtime_spec(
                session.tenant_id, session.agent_id, session.agent_version_id,
                session_id=session.id, context=session.session_context_json,
            )
            self.assertEqual(spec.agent_version_id, v1)
            self.assertEqual(spec.instructions.system_prompt, "Prompt v1")
            self.assertNotEqual(spec.agent_version_id, v3_id)
            self.assertEqual(session.agent_version_id, v1)
            # a new default session picks the new published version; the pinned one is untouched
            self.assertEqual(VoiceSessionService(db).create(
                self.tenant.id, agent_id, channel="internal_test", direction="internal").agent_version_id, v3_id)


class ExactAgentVersionBoundaryTests(unittest.TestCase):
    APP = Path(__file__).parent / "app" / "modules"

    def test_voice_reaches_agent_builder_only_through_its_public_api(self) -> None:
        for path in (self.APP / "voice").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules = [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
                modules += [a.name for a in node.names] if isinstance(node, ast.Import) else []
                for module in modules:
                    if module.startswith("app.modules.agents"):
                        self.assertEqual(module, "app.modules.agents.public", f"{path}: {module}")

    def test_new_runtime_target_code_has_no_provider_specific_logic(self) -> None:
        from app.modules.agents.application.queries import AgentQueries

        for function in (AgentQueries.resolve_runtime_target, VoiceSessionService.create_from_agent_version,
                         VoiceSessionService._create_session):
            self.assertNotIn("ultravox", inspect.getsource(function).lower(), function.__qualname__)

    def test_voice_public_import_stays_light(self) -> None:
        import subprocess
        import sys

        code = ("import sys; import app.modules.voice.public; "
                "assert not any(m.startswith('app.modules.agents.infrastructure') for m in sys.modules)")
        subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent, check=True)


if __name__ == "__main__":
    unittest.main()
