"""Agent Builder -- public API.

The only import path other modules may use for Agent Builder. Nothing
returned here is an ORM row: TenantAgent / TenantAgentVersion and their
JSON columns (runtime_binding_json, ...) stay inside this module.

Top-level imports are deliberately limited to pure domain contracts and
errors: RuntimeSessionSpecV1 (owned by Voice) imports the agent value
objects from here, and the compiler imports RuntimeSessionSpecV1, so the
use cases are imported lazily inside the facade methods.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.modules.agents.domain.contracts import (
    AgentBehavior,
    AgentIdentity,
    AgentInstructions,
    AgentToolBinding,
    AgentVoiceConfig,
)
from app.modules.agents.domain.errors import (
    AgentCompilerError,
    AgentConflictError,
    AgentNotFoundError,
    AgentValidationError,
    VoiceSelectionError,
)
from app.modules.agents.domain.views import (
    AgentDisplay,
    AgentToolBindingView,
    ImportedAgent,
    PublishedAgent,
    PublishedAgentUnavailableError,
)

if TYPE_CHECKING:
    from app.modules.voice_providers.public import ProviderAgentImport
    from app.schemas.runtime_session import RuntimeSessionSpecV1

__all__ = [
    "AgentBehavior",
    "AgentCompilerError",
    "AgentConflictError",
    "AgentDisplay",
    "AgentIdentity",
    "AgentInstructions",
    "AgentNotFoundError",
    "AgentToolBinding",
    "AgentToolBindingView",
    "AgentValidationError",
    "AgentVoiceConfig",
    "AgentsFacade",
    "ImportedAgent",
    "PublishedAgent",
    "PublishedAgentUnavailableError",
    "VoiceSelectionError",
    "validate_voice_settings",
]


def validate_voice_settings(voice: AgentVoiceConfig) -> None:
    """The provider-specific settings rules (e.g. ElevenLabs keys/ranges) of
    a voice selection, without registry/provider context. Raises
    VoiceSelectionError."""
    from app.modules.agents.domain.voice_selection import VoiceSelectionService

    VoiceSelectionService.validate_settings(voice)


class AgentsFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- reads for Voice / Tool Platform -------------------------------------

    def lock_published_agent(self, tenant_id: str, agent_id: str) -> PublishedAgent:
        """Locks the agent row (SELECT ... FOR UPDATE) for the caller's
        transaction and returns its published version. Raises
        PublishedAgentUnavailableError."""
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).lock_published_agent(tenant_id, agent_id)

    def get_agent_status(self, tenant_id: str, agent_id: str) -> str | None:
        """Current status straight from the database (never a cached row)."""
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).agent_status(tenant_id, agent_id)

    def get_tool_bindings(self, tenant_id: str, agent_version_id: str) -> tuple[AgentToolBindingView, ...]:
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).tool_bindings(tenant_id, agent_version_id)

    def describe_agent(self, tenant_id: str, agent_id: str, agent_version_id: str | None) -> AgentDisplay:
        """Agent name/status, falling back to the version's identity name
        when the agent row is gone (status None)."""
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).describe(tenant_id, agent_id, agent_version_id)

    def agent_names(self, tenant_id: str, agent_ids: Iterable[str]) -> dict[str, str]:
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).names(tenant_id, agent_ids)

    def is_tool_bound_to_published_version(self, tenant_id: str, tool_key: str) -> bool:
        from app.modules.agents.application.queries import AgentQueries

        return AgentQueries(self.db).is_tool_bound_to_published_version(tenant_id, tool_key)

    # -- use cases -------------------------------------------------------------

    def compile_runtime_spec(
        self,
        tenant_id: str,
        agent_id: str,
        agent_version_id: str,
        *,
        session_id: str | None,
        context: Mapping[str, Any] | None,
    ) -> RuntimeSessionSpecV1:
        """Raises AgentCompilerError."""
        from app.modules.agents.wiring import agent_compiler

        return agent_compiler(self.db).compile_version(
            tenant_id, agent_id, agent_version_id, session_id=session_id, context=dict(context or {})
        )

    def import_provider_agent(self, tenant_id: str, user_id: str | None, snapshot: ProviderAgentImport) -> ImportedAgent:
        """Creates a draft agent from a provider-side snapshot. Raises
        AgentValidationError / FeatureDisabledError."""
        from app.modules.agents.wiring import agent_service

        return agent_service(self.db).import_provider_agent(tenant_id, user_id, snapshot)
