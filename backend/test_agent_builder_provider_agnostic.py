"""Agent Builder no longer depends on Ultravox, structurally or semantically.

- A fake, non-Ultravox provider ("acme") satisfying VoiceProviderPort is
  enough to link/validate a provider_managed agent, validate a voice,
  publish, and import a provider agent snapshot. The Ultravox adapter is
  booby-trapped so any accidental use fails the test.
- An Ultravox import still persists exactly the runtime_binding_json shape
  the runtime has always received.
- A legacy agent (voice_agent_config_id, no realtime.voice) still compiles
  to the same RuntimeSessionSpecV1, via voice_legacy.public.
"""

from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack
from types import MappingProxyType
from typing import ClassVar
from unittest.mock import patch

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.domain import voice_registry
from app.models.integrations import TenantVoiceAgentConfig
from app.modules.agents.api.schemas import AgentCreateRequest
from app.modules.agents.application.ports import AgentPorts
from app.modules.agents.application.service import AgentService
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.agents.public import AgentsFacade, AgentValidationError
from app.modules.voice_providers.public import (
    ProviderAgentImport,
    ProviderAgentSnapshot,
    ProviderToolRef,
    ProviderVoiceSelection,
    VoiceProviderError,
)
from app.services.tenant_feature_service import AGENT_BUILDER, TenantFeatureService


class FakeVoiceProvider:
    """VoiceProviderPort for a provider that is not Ultravox."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.voice_error: str | None = None

    def supports_provider_managed(self, provider: str) -> bool:
        return provider == "acme"

    def link_provider_agent(self, tenant_id: str, provider: str, agent_ref: str) -> ProviderAgentSnapshot:
        self.calls.append(("link", provider, agent_ref))
        return ProviderAgentSnapshot(
            provider=provider, agent_ref=agent_ref, revision_ref="rev-7",
            tools=(ProviderToolRef(name="lookup", classification="provider_native"),),
            has_unsupported_client_tools=False,
        )

    def validate_provider_execution(self, tenant_id: str, provider: str, agent_ref: str) -> None:
        self.calls.append(("execution", provider, agent_ref))

    def validate_voice(self, tenant_id: str, realtime_provider: str, voice: ProviderVoiceSelection) -> None:
        self.calls.append(("voice", realtime_provider, voice))
        if self.voice_error:
            raise VoiceProviderError(self.voice_error)


class AlwaysConfigured:
    def is_configured(self, tenant_id: str, integration: str | None) -> bool:
        return True


class NoLegacyVoice:
    def get_voice_agent_defaults(self, tenant_id: str, config_id: str):
        return None


class NoSessions:
    async def release_sessions_of_deleted_agent(self, tenant_id: str, agent_id: str) -> None:
        return None


def _acme_catalog(stack: ExitStack) -> None:
    """Registers a fictitious realtime provider in Voice's catalog -- the only
    place that has to know about a provider for Agent Builder to accept it."""
    stack.enter_context(patch.dict(voice_registry._PROVIDERS_BY_KEY, {
        "acme": voice_registry.VoiceProvider(
            key="acme", name="Acme", status="active", supports_managed_credentials=False, supports_byok=True
        ),
    }))
    stack.enter_context(patch.dict(voice_registry._MODELS_BY_ID, {
        "acme:acme-rt": voice_registry.VoiceModel(
            id="acme:acme-rt", provider_key="acme", key="acme-rt", name="Acme Realtime",
            execution_model_id="acme/realtime-1", model_type="realtime", implementation_status="available",
            capabilities={"provider_voice": True},
        ),
    }))


class ProviderAgnosticAgentBuilderTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.tenant.id, AGENT_BUILDER, True, {}, self.user.id)
        self.provider = FakeVoiceProvider()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        _acme_catalog(self.stack)
        # Any use of the Ultravox adapter from Agent Builder is a failure.
        self.stack.enter_context(patch(
            "app.services.ultravox_admin_service.UltravoxAdminService.__init__",
            side_effect=AssertionError("Agent Builder must not reach the Ultravox adapter"),
        ))

    def _service(self, db) -> AgentService:
        return AgentService(db, AgentPorts(
            voice_provider=self.provider,
            legacy_voice=NoLegacyVoice(),
            integrations=AlwaysConfigured(),
            voice_sessions=NoSessions(),
        ))

    def test_provider_managed_agent_links_and_publishes_through_the_port(self) -> None:
        with SessionLocal() as db:
            service = self._service(db)
            agent = service.create_agent(self.tenant.id, AgentCreateRequest(
                name="Acme agent", provider="acme", model="acme-rt",
                management_mode="provider_managed", provider_agent={"agent_id": "remote-1"},
            ), self.user.id)
            realtime = agent.draft_version.runtime_binding_json["realtime"]
            self.assertEqual(realtime["provider_agent"], {"agent_id": "remote-1", "observed_published_revision_id": "rev-7"})
            self.assertEqual(realtime["provider_extensions"], {
                "tools": [{"name": "lookup", "classification": "provider_native"}],
                "has_unsupported_client_tools": False,
            })
            published = service.publish(self.tenant.id, agent.id, self.user.id)
        self.assertEqual(published.status, "active")
        self.assertEqual(self.provider.calls, [("link", "acme", "remote-1"), ("execution", "acme", "remote-1")])

    def test_unsupported_provider_managed_provider_keeps_its_stable_error(self) -> None:
        with SessionLocal() as db, self.assertRaisesRegex(AgentValidationError, "Unsupported provider-managed"):
            self._service(db).create_agent(self.tenant.id, AgentCreateRequest(
                name="x", provider="ultravox", model="ultravox-v0.7",
                management_mode="provider_managed", provider_agent={"agent_id": "remote-1"},
            ), self.user.id)

    def test_voice_is_validated_through_the_port_on_publish(self) -> None:
        body = AgentCreateRequest(
            name="Acme voice", provider="acme", model="acme-rt",
            instructions={"system_prompt": "Hola"},
            voice={"mode": "provider", "provider": "acme", "voice_id": "v-1"},
        )
        with SessionLocal() as db:
            service = self._service(db)
            agent = service.create_agent(self.tenant.id, body, self.user.id)
            self.provider.voice_error = "voice_not_accessible"
            with self.assertRaisesRegex(AgentValidationError, "voice_not_accessible"):
                service.publish(self.tenant.id, agent.id, self.user.id)
            self.provider.voice_error = None
            self.assertEqual(service.publish(self.tenant.id, agent.id, self.user.id).status, "active")
        _, realtime_provider, selection = self.provider.calls[-1]
        self.assertEqual(realtime_provider, "acme")
        self.assertEqual((selection.mode, selection.provider, selection.voice_id), ("provider", "acme", "v-1"))

    def test_imports_a_provider_agent_snapshot_and_compiles_it(self) -> None:
        snapshot = ProviderAgentImport(
            provider="acme", provider_agent_id="remote-9", provider_revision_id="rev-2",
            name="Imported", language="es-CO", system_prompt="Eres Ana.", model="acme-rt", voice_id="v-9",
            tools=(
                ProviderToolRef(name="book", classification="serviglobal_supported"),
                ProviderToolRef(name="hangUp", classification="provider_native"),
            ),
            provider_settings=MappingProxyType({"temperature": 0.4}),
        )
        with SessionLocal() as db:
            imported = self._service(db).import_provider_agent(self.tenant.id, self.user.id, snapshot)
            draft = db.get(TenantAgentVersion, imported.draft_version_id)
            self.assertEqual(imported.warnings, ("Tool 'hangUp' remains provider_only.",))
            self.assertEqual(draft.instructions_json["system_prompt"], "Eres Ana.")
            self.assertEqual(draft.identity_json["name"], "Imported")
            self.assertEqual(draft.runtime_binding_json["realtime"]["provider_extensions"]["source"], "acme_import")
            self.assertEqual(
                draft.runtime_binding_json["realtime"]["voice"],
                {"mode": "provider", "provider": "acme", "voice_id": "v-9"},
            )
            draft.status = "published"
            db.commit()
            spec = AgentsFacade(db).compile_runtime_spec(
                self.tenant.id, imported.agent_id, imported.draft_version_id, session_id=None, context=None
            )
        self.assertEqual(spec.runtime.realtime.provider, "acme")
        self.assertEqual(spec.runtime.realtime.model, "acme/realtime-1")


class _FakeUltravoxClient:
    RAW_AGENT: ClassVar[dict] = {
        "agentId": "uv-agent-1",
        "publishedRevisionId": "uv-rev-3",
        "name": "Recepción",
        "callTemplate": {
            "systemPrompt": "Eres la recepcionista.",
            "languageHint": "es",
            "voice": "Jessica",
            "temperature": 0.3,
            "firstSpeaker": "FIRST_SPEAKER_AGENT",
            "maxDuration": "600s",
            "vadSettings": {"turnEndpointDelay": "0.4s", "apiKey": "must-be-dropped"},
            "selectedTools": [
                {"toolName": "check_availability"},
                {"toolName": "hangUp"},
                {"toolName": "browserTool", "client": {}},
            ],
        },
    }

    def get_agent(self, api_key: str, agent_id: str) -> dict:
        return dict(self.RAW_AGENT, agentId=agent_id)


class UltravoxImportShapeTests(Integration2ATestCase):
    """The import moved from UltravoxAdminService to Agent Builder; the
    persisted runtime_binding_json must be exactly what it always was."""

    def setUp(self) -> None:
        super().setUp()
        with SessionLocal() as db:
            TenantFeatureService(db).set_feature(self.tenant.id, AGENT_BUILDER, True, {}, self.user.id)

    def test_ultravox_import_persists_the_legacy_runtime_binding_shape(self) -> None:
        from app.services.ultravox_admin_service import UltravoxAdminService

        with SessionLocal() as db:
            from app.modules.voice_providers.public import VoiceProviderFacade

            adapter = UltravoxAdminService(db, client=_FakeUltravoxClient())
            with (
                patch.object(UltravoxAdminService, "_api_key", return_value="key"),
                patch.object(VoiceProviderFacade, "_adapter", return_value=adapter),
            ):
                snapshot = VoiceProviderFacade(db).get_agent_import(self.tenant.id, "ultravox", "uv-agent-1")
            imported = AgentsFacade(db).import_provider_agent(self.tenant.id, self.user.id, snapshot)
            draft = db.get(TenantAgentVersion, imported.draft_version_id)
            agent = db.get(TenantAgent, imported.agent_id)
            warnings = [
                "Tool 'hangUp' remains provider_only.",
                "Tool 'browserTool' remains provider_only.",
            ]
            self.assertEqual(list(imported.warnings), warnings)
            self.assertEqual(agent.name, "Recepción")
            self.assertEqual(agent.status, "draft")
            self.assertEqual(draft.language, "es")
            self.assertEqual(draft.instructions_json["system_prompt"], "Eres la recepcionista.")
            self.assertEqual(draft.runtime_binding_json, {
                "pipeline_type": "realtime",
                "realtime": {
                    "provider": "ultravox",
                    "model": "ultravox-v0.7",
                    "management_mode": "serviglobal_managed",
                    "provider_extensions": {
                        "source": "ultravox_import",
                        "source_agent_id": "uv-agent-1",
                        "source_revision_id": "uv-rev-3",
                        "tools": [
                            {"name": "check_availability", "classification": "serviglobal_supported"},
                            {"name": "hangUp", "classification": "provider_native"},
                            {"name": "browserTool", "classification": "unsupported_client_tool"},
                        ],
                        "warnings": warnings,
                        "temperature": 0.3,
                        "first_speaker": "FIRST_SPEAKER_AGENT",
                        "max_duration": "600s",
                        "vad_settings": {"turnEndpointDelay": "0.4s"},
                    },
                    "voice": {"mode": "provider", "provider": "ultravox", "voice_id": "Jessica"},
                },
            })


class LegacyVoiceAgentCompileTests(Integration2ATestCase):
    def test_legacy_default_voice_compiles_to_the_same_runtime_spec(self) -> None:
        with SessionLocal() as db:
            config = TenantVoiceAgentConfig(
                tenant_id=self.tenant.id, provider="ultravox", provider_agent_id="va-legacy",
                display_name="Legacy", default_voice="nova", default_system_prompt="legacy",
            )
            agent = TenantAgent(tenant_id=self.tenant.id, name="Legacy", status="active")
            db.add_all([config, agent])
            db.flush()
            version = TenantAgentVersion(
                tenant_id=self.tenant.id, agent_id=agent.id, version=1, status="published",
                language="es", timezone="America/Bogota", identity_json={"name": "Legacy"},
                instructions_json={"system_prompt": "Hola"}, behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox", "model": "ultravox"}},
                voice_agent_config_id=config.id,
            )
            db.add(version)
            db.commit()
            spec = AgentsFacade(db).compile_runtime_spec(
                self.tenant.id, agent.id, version.id, session_id="s-1", context=None
            )
        realtime = spec.runtime.realtime
        self.assertEqual(
            (realtime.voice.mode, realtime.voice.provider, realtime.voice.voice_id), ("provider", "ultravox", "nova")
        )
        self.assertEqual(realtime.voice.settings, {})
        self.assertEqual(realtime.settings["voice"], "nova")  # legacy bridge, kept on purpose
        self.assertEqual(realtime.model, "fixie-ai/ultravox")


class ToolBindingViewTests(unittest.TestCase):
    def test_non_dict_binding_config_is_normalized_to_empty_invalid_data(self) -> None:
        # Invalid data, not a supported contract: the draft schema already
        # rejects a non-dict `config`; the read view just stays defensive.
        from app.modules.agents.domain.views import tool_binding_views
        from app.modules.agents.public import AgentToolBindingView

        views = tool_binding_views({"tools": [{"key": "custom.crm_lookup", "config": ["not", "a", "dict"]}]})
        self.assertEqual(views, (AgentToolBindingView(key="custom.crm_lookup", enabled=True, config=MappingProxyType({})),))
        self.assertEqual(dict(views[0].config), {})


class VoiceProviderFacadeTests(unittest.TestCase):
    def test_provider_errors_become_provider_agnostic(self) -> None:
        from app.modules.voice_providers.public import VoiceProviderFacade
        from app.services.ultravox_provider_client import UltravoxProviderError

        class Adapter:
            def get_voice(self, tenant_id, voice_id):
                raise UltravoxProviderError("provider_resource_not_found", 404)

            def validate_execution_preflight(self, tenant_id, agent_id):
                raise ValueError("provider_agent_has_unsupported_client_tools")

        facade = VoiceProviderFacade(db=None)
        with patch.object(VoiceProviderFacade, "_adapter", return_value=Adapter()):
            with self.assertRaises(VoiceProviderError) as voice_ctx:
                facade.validate_voice("t", "ultravox", ProviderVoiceSelection("provider", "ultravox", "Mark"))
            with self.assertRaises(VoiceProviderError) as exec_ctx:
                facade.validate_provider_execution("t", "ultravox", "a")
        self.assertEqual(voice_ctx.exception.code, "voice_not_accessible")
        self.assertEqual(exec_ctx.exception.code, "provider_agent_has_unsupported_client_tools")
        self.assertNotIsInstance(voice_ctx.exception, UltravoxProviderError)


class VoiceSessionsReleaseTests(unittest.TestCase):
    def test_busy_session_maps_to_the_same_agent_conflict_code(self) -> None:
        from app.modules.agents.domain.errors import AgentConflictError
        from app.modules.voice.public import VoiceSessionsBusyError

        class Busy:
            async def release_sessions_of_deleted_agent(self, tenant_id, agent_id):
                raise VoiceSessionsBusyError("agent_delete_session_dispatching")

        agent = TenantAgent(id="a", tenant_id="t", name="x", status="archived")
        service = AgentService(db=None, ports=AgentPorts(
            voice_provider=FakeVoiceProvider(), legacy_voice=NoLegacyVoice(),
            integrations=AlwaysConfigured(), voice_sessions=Busy(),
        ))
        with (
            patch.object(AgentService, "_locked_agent", return_value=agent),
            self.assertRaisesRegex(AgentConflictError, "agent_delete_session_dispatching"),
        ):
            asyncio.run(service.delete_agent("t", "a", None))


if __name__ == "__main__":
    unittest.main()
