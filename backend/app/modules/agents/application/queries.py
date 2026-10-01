"""Read-side queries other modules need about agents. Each one returns a
frozen view (app.modules.agents.domain.views), never an ORM row; they
replace the TenantAgent/TenantAgentVersion queries Voice and Tool Platform
used to run themselves."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.agents.domain.views import (
    AgentDisplay,
    AgentToolBindingView,
    PublishedAgent,
    PublishedAgentUnavailableError,
    tool_binding_views,
)
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion


class AgentQueries:
    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_published_agent(self, tenant_id: str, agent_id: str) -> PublishedAgent:
        agent = self.db.scalar(
            select(TenantAgent)
            .where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id)
            .with_for_update()
        )
        if agent is None or agent.status != "active" or not agent.published_version_id:
            raise PublishedAgentUnavailableError("agent_not_active")
        version = self.db.scalar(
            select(TenantAgentVersion).where(
                TenantAgentVersion.id == agent.published_version_id,
                TenantAgentVersion.agent_id == agent.id,
                TenantAgentVersion.tenant_id == tenant_id,
                TenantAgentVersion.status == "published",
            )
        )
        if version is None:
            raise PublishedAgentUnavailableError("published_version_invalid")
        runtime = version.runtime_binding_json or {}
        realtime = runtime.get("realtime")
        return PublishedAgent(
            agent_id=agent.id,
            tenant_id=tenant_id,
            version_id=version.id,
            pipeline_type=runtime.get("pipeline_type"),
            realtime_provider=realtime.get("provider", "") if isinstance(realtime, dict) else None,
        )

    def agent_status(self, tenant_id: str, agent_id: str) -> str | None:
        # A column query always reads the database, so a concurrent
        # archival is seen even if this Session holds a stale TenantAgent.
        return self.db.scalar(
            select(TenantAgent.status).where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id)
        )

    def tool_bindings(self, tenant_id: str, agent_version_id: str) -> tuple[AgentToolBindingView, ...]:
        runtime = self.db.scalar(
            select(TenantAgentVersion.runtime_binding_json).where(
                TenantAgentVersion.id == agent_version_id, TenantAgentVersion.tenant_id == tenant_id
            )
        )
        return tool_binding_views(runtime)

    def describe(self, tenant_id: str, agent_id: str, agent_version_id: str | None) -> AgentDisplay:
        agent = self.db.scalar(
            select(TenantAgent).where(TenantAgent.id == agent_id, TenantAgent.tenant_id == tenant_id)
        )
        if agent is not None:
            return AgentDisplay(name=agent.name, status=agent.status)
        identity = (
            self.db.scalar(
                select(TenantAgentVersion.identity_json).where(
                    TenantAgentVersion.id == agent_version_id, TenantAgentVersion.tenant_id == tenant_id
                )
            )
            if agent_version_id
            else None
        )
        return AgentDisplay(name=(identity or {}).get("name"), status=None)

    def names(self, tenant_id: str, agent_ids: Iterable[str]) -> dict[str, str]:
        ids = {agent_id for agent_id in agent_ids if agent_id}
        if not ids:
            return {}
        return dict(
            self.db.execute(
                select(TenantAgent.id, TenantAgent.name).where(
                    TenantAgent.tenant_id == tenant_id, TenantAgent.id.in_(ids)
                )
            ).all()
        )

    def is_tool_bound_to_published_version(self, tenant_id: str, tool_key: str) -> bool:
        runtimes = self.db.scalars(
            select(TenantAgentVersion.runtime_binding_json).where(
                TenantAgentVersion.tenant_id == tenant_id, TenantAgentVersion.status == "published"
            )
        ).all()
        return any(view.key == tool_key for runtime in runtimes for view in tool_binding_views(runtime))
