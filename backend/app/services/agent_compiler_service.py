from __future__ import annotations

from pydantic import ValidationError

from app.models.agents import TenantAgent, TenantAgentVersion
from app.schemas.agents import AgentBehavior, AgentIdentity, AgentInstructions
from app.schemas.runtime_session import RuntimeSessionSpecV1


class AgentCompilerError(ValueError):
    pass


class AgentCompilerService:
    """Compiles an Agent Builder Agent + AgentVersion into a
    RuntimeSessionSpecV1 -- the typed contract a future voice runtime
    consumes. Resolves nothing from providers and carries no secrets; that
    stays the job of the runtime adapter (see agent_runtime_adapter.py) and,
    eventually, a credential resolver in the runtime process itself.
    """

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
                runtime=version.runtime_binding_json,
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
    context: dict | None = None,
    session_id: str | None = None,
    allow_draft: bool = False,
) -> RuntimeSessionSpecV1:
    """Module-level convenience wrapper around AgentCompilerService.compile,
    kept for callers that don't need to hold a service instance."""
    return AgentCompilerService().compile(
        agent,
        version,
        context=context,
        session_id=session_id,
        allow_draft=allow_draft,
    )
