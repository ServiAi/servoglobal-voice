from __future__ import annotations

import os
import unittest

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./serviai_agent_compiler_test.db")

from app.models.agents import TenantAgent, TenantAgentVersion
from app.services.agent_compiler_service import (
    AgentCompilerError,
    AgentCompilerService,
    compile_runtime_session_spec,
)


def _agent(**overrides) -> TenantAgent:
    defaults = dict(
        id="agent-1",
        tenant_id="tenant-1",
        name="Sandra",
        description="Asesora comercial",
        status="active",
        published_version_id="version-1",
        draft_version_id=None,
    )
    defaults.update(overrides)
    return TenantAgent(**defaults)


def _published_version(**overrides) -> TenantAgentVersion:
    defaults = dict(
        id="version-1",
        agent_id="agent-1",
        tenant_id="tenant-1",
        version=1,
        status="published",
        language="es",
        timezone="America/Bogota",
        identity_json={"name": "Sandra", "description": "Asesora comercial"},
        instructions_json={
            "role": "Asesora comercial",
            "objective": "Agendar una cita",
            "system_prompt": "Eres Sandra, asesora comercial.",
            "greeting": "Hola",
            "closing": "Gracias",
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
    defaults.update(overrides)
    return TenantAgentVersion(**defaults)


class AgentCompilerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compiler = AgentCompilerService()

    def test_compiles_published_version_into_runtime_session_spec_v1(self) -> None:
        agent = _agent()
        version = _published_version()
        spec = self.compiler.compile(agent, version)

        self.assertEqual(spec.spec_version, "1")
        self.assertEqual(spec.tenant_id, "tenant-1")
        self.assertEqual(spec.agent_id, "agent-1")
        self.assertEqual(spec.agent_version_id, "version-1")
        self.assertEqual(spec.identity.name, "Sandra")
        self.assertEqual(spec.identity.description, "Asesora comercial")
        self.assertEqual(spec.instructions.system_prompt, "Eres Sandra, asesora comercial.")
        self.assertEqual(spec.behavior.response_style, "balanced")
        self.assertEqual(spec.language, "es")
        self.assertEqual(spec.timezone, "America/Bogota")
        self.assertEqual(spec.runtime.pipeline_type, "realtime")
        self.assertEqual(spec.runtime.realtime.provider, "ultravox")
        self.assertEqual(spec.runtime.realtime.model, "ultravox")
        self.assertEqual(spec.context, {})
        self.assertIsNone(spec.session_id)

    def test_module_level_wrapper_matches_service_output(self) -> None:
        agent = _agent()
        version = _published_version()
        spec = compile_runtime_session_spec(agent, version)
        self.assertEqual(spec.agent_version_id, "version-1")

    def test_context_is_passed_through_explicitly(self) -> None:
        agent = _agent()
        version = _published_version()
        spec = self.compiler.compile(agent, version, context={"lead_id": "lead-9"})
        self.assertEqual(spec.context, {"lead_id": "lead-9"})

    def test_session_id_is_passed_through(self) -> None:
        agent = _agent()
        version = _published_version()
        spec = self.compiler.compile(agent, version, session_id="session-123")
        self.assertEqual(spec.session_id, "session-123")

    def test_refuses_draft_version_by_default(self) -> None:
        agent = _agent(status="draft", published_version_id=None, draft_version_id="version-1")
        version = _published_version(status="draft")
        with self.assertRaises(AgentCompilerError):
            self.compiler.compile(agent, version)

    def test_allows_draft_version_when_explicitly_requested(self) -> None:
        agent = _agent(status="draft", published_version_id=None, draft_version_id="version-1")
        version = _published_version(status="draft")
        spec = self.compiler.compile(agent, version, allow_draft=True)
        self.assertEqual(spec.agent_version_id, "version-1")

    def test_compile_published_uses_agents_published_version_relationship(self) -> None:
        agent = _agent()
        version = _published_version()
        agent.published_version = version
        spec = self.compiler.compile_published(agent)
        self.assertEqual(spec.agent_version_id, "version-1")

    def test_compile_published_fails_without_a_published_version(self) -> None:
        agent = _agent(published_version_id=None)
        agent.published_version = None
        with self.assertRaises(AgentCompilerError):
            self.compiler.compile_published(agent)

    def test_tenant_mismatch_raises(self) -> None:
        agent = _agent(tenant_id="tenant-1")
        version = _published_version(tenant_id="tenant-2")
        with self.assertRaises(AgentCompilerError):
            self.compiler.compile(agent, version)

    def test_agent_mismatch_raises(self) -> None:
        agent = _agent(id="agent-1")
        version = _published_version(agent_id="agent-other")
        with self.assertRaises(AgentCompilerError):
            self.compiler.compile(agent, version)

    def test_invalid_runtime_binding_raises(self) -> None:
        agent = _agent()
        version = _published_version(
            runtime_binding_json={"pipeline_type": "quantum", "made_up": True}
        )
        with self.assertRaises(AgentCompilerError):
            self.compiler.compile(agent, version)

    def test_result_never_contains_provider_secrets(self) -> None:
        # Even if a caller stuffed provider-style keys into behavior/context,
        # the compiler must not merge in anything from TenantVoiceAgentConfig
        # (api keys, encrypted secrets) -- it never even receives that model.
        agent = _agent()
        version = _published_version()
        spec = self.compiler.compile(agent, version, context={"note": "plain context value"})
        dumped = spec.model_dump_json()
        for forbidden in ("api_key", "secret", "token", "password", "Bearer"):
            self.assertNotIn(forbidden, dumped)


if __name__ == "__main__":
    unittest.main()
