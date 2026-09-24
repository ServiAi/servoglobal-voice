from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.resolved_tool import ResolvedToolDefinition, from_platform
from app.domain.tool_registry import get_tool
from app.domain.voice_registry import VoiceRegistryValidationError, resolve_execution_model_id
from app.models.agents import TenantAgent, TenantAgentVersion
from app.schemas.agents import AgentBehavior, AgentIdentity, AgentInstructions
from app.schemas.runtime_session import RuntimeSessionSpecV1
from app.services.platform_tool_contract_service import PlatformToolContractService


class AgentCompilerError(ValueError):
    pass


class AgentCompilerService:
    """Compiles an Agent Builder Agent + AgentVersion into a
    RuntimeSessionSpecV1 -- the typed contract the voice runtime consumes.
    Resolves nothing from providers and carries no secrets; that stays the
    job of the runtime process itself (see
    voice-runtime/src/serviglobal_voice_runtime/providers.py for the
    per-provider execution adapters, and .../credentials.py for the
    per-VoiceSession credential resolver).

    `db` is optional and only needed to resolve custom.* tool bindings
    (via ToolResolverService) -- platform tool bindings resolve from the
    static Registry either way, so callers that never bind custom tools
    (and existing tests) can keep constructing this with no arguments.
    """

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def compile(
        self,
        agent: TenantAgent,
        version: TenantAgentVersion,
        *,
        context: dict | None = None,
        session_id: str | None = None,
        allow_draft: bool = False,
    ) -> RuntimeSessionSpecV1:
        self._validate_relationship(agent, version)
        if not allow_draft and version.status == "draft":
            raise AgentCompilerError(
                "Refusing to compile a draft version. Pass allow_draft=True "
                "explicitly for preview/test use -- production execution "
                "must compile the published version only."
            )
        runtime_binding = dict(version.runtime_binding_json)
        realtime = runtime_binding.get("realtime")
        voice_config = version.voice_agent_config
        if isinstance(realtime, dict):
            realtime = dict(realtime)
            realtime.setdefault("management_mode", "serviglobal_managed")
            try:
                realtime["model"] = resolve_execution_model_id(
                    str(realtime.get("provider") or ""),
                    str(realtime.get("model") or ""),
                )
            except VoiceRegistryValidationError as exc:
                raise AgentCompilerError(f"Invalid runtime binding: {exc}") from exc

            # New voice contract (schemas.agents.AgentVoiceConfig shape): if a
            # draft or an Ultravox import already populated realtime.voice, it
            # is the source of truth and is left untouched. Otherwise,
            # synthesize one from the legacy TenantVoiceAgentConfig link so
            # old and new agents compile to the same shape.
            if not realtime.get("voice") and voice_config and voice_config.default_voice:
                realtime["voice"] = {
                    "mode": "provider", "provider": "ultravox",
                    "voice_id": voice_config.default_voice, "settings": {},
                }

            # Keep the legacy settings.voice bridge for older runtime consumers.
            # The current runtime prefers realtime.voice when present.
            if voice_config and voice_config.default_voice:
                realtime["settings"] = {
                    "voice": voice_config.default_voice,
                    **realtime.get("settings", {}),
                }
            runtime_binding["realtime"] = realtime

        # Resolve runtime_binding_json["tools"] (key/enabled/config) into
        # the compiled shape the runtime actually needs (key/name/
        # description/input_schema), dropping `config` -- the tool-invoke
        # endpoint re-resolves it itself, so it never needs to transit
        # through the runtime/LLM. Defensive by design: an unknown or
        # no-longer-available key on an already-published version is
        # skipped rather than raising -- the hard validation already
        # happened at publish time (AgentService._publish_tools_preflight);
        # compiling a published version must never fail because the
        # Registry changed afterwards.
        compiled_tools = []
        for binding in runtime_binding.pop("tools", []) or []:
            if not isinstance(binding, dict) or not binding.get("enabled", True):
                continue
            resolved = self._resolve_tool(agent.tenant_id, str(binding.get("key") or ""))
            if resolved is None or resolved.status != "available":
                continue
            # Only tools with a real binding_config_schema (today: just
            # whatsapp.send_message) need a per-binding effective schema;
            # every other platform/custom tool keeps its static
            # input_schema, unchanged from before this refactor.
            config = binding.get("config") if isinstance(binding.get("config"), dict) else {}
            input_schema = (
                PlatformToolContractService(self.db).compile_llm_schema(resolved, config)
                if resolved.binding_config_schema
                else resolved.input_schema
            )
            compiled_tools.append({
                "key": resolved.key, "name": resolved.name,
                "description": resolved.description, "input_schema": input_schema,
            })

        try:
            return RuntimeSessionSpecV1(
                session_id=session_id,
                tenant_id=agent.tenant_id,
                agent_id=agent.id,
                agent_version_id=version.id,
                identity=AgentIdentity.model_validate(version.identity_json),
                instructions=AgentInstructions.model_validate(version.instructions_json),
                behavior=AgentBehavior.model_validate(version.behavior_json),
                language=version.language,
                timezone=version.timezone,
                runtime=runtime_binding,
                tools=compiled_tools,
                context=context or {},
            )
        except ValidationError as exc:
            raise AgentCompilerError(f"Invalid runtime binding: {exc}") from exc

    def compile_published(
        self,
        agent: TenantAgent,
        *,
        context: dict | None = None,
        session_id: str | None = None,
    ) -> RuntimeSessionSpecV1:
        """The only entry point a real execution flow should use: always
        compiles agent.published_version, never whatever happens to be the
        current draft."""
        if agent.published_version is None:
            raise AgentCompilerError("Agent has no published version to compile.")
        return self.compile(
            agent, agent.published_version, context=context, session_id=session_id
        )

    def _resolve_tool(self, tenant_id: str, key: str) -> ResolvedToolDefinition | None:
        if self.db is not None:
            from app.services.tool_resolver_service import ToolResolverService

            return ToolResolverService(self.db).resolve(tenant_id, key)
        if key.startswith("custom."):
            return None
        tool = get_tool(key)
        return from_platform(tool) if tool is not None else None

    @staticmethod
    def _validate_relationship(agent: TenantAgent, version: TenantAgentVersion) -> None:
        if version.agent_id != agent.id:
            raise AgentCompilerError("Version does not belong to this agent.")
        if version.tenant_id != agent.tenant_id:
            raise AgentCompilerError("Version tenant does not match agent tenant.")


def compile_runtime_session_spec(
    agent: TenantAgent,
    version: TenantAgentVersion,
    *,
    db: Session | None = None,
    context: dict | None = None,
    session_id: str | None = None,
    allow_draft: bool = False,
) -> RuntimeSessionSpecV1:
    """Module-level convenience wrapper around AgentCompilerService.compile,
    kept for callers that don't need to hold a service instance. Pass `db`
    to resolve custom.* tool bindings; omit it for platform-tools-only use
    (existing callers/tests are unaffected)."""
    return AgentCompilerService(db).compile(
        agent,
        version,
        context=context,
        session_id=session_id,
        allow_draft=allow_draft,
    )
