"""Analytics agent projection: the reporting/provider dimension (``agents`` table).

Not the Agent Builder identity (``tenant_agents``): this is only what calls and
dashboards join against."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.analytics.application.views import agent_view
from app.modules.analytics.contracts import AgentUpsertCommand, AnalyticsAgentView, NewAgentCommand
from app.modules.analytics.domain.errors import AmbiguousAnalyticsAgentError, AnalyticsAgentNotFoundError
from app.modules.analytics.infrastructure.models import Agent


class AnalyticsAgentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, tenant_id: str, agent_id: str) -> AnalyticsAgentView | None:
        agent = self.db.get(Agent, agent_id)
        return agent_view(agent) if agent is not None and agent.tenant_id == tenant_id else None

    def find_by_provider_identity(
        self, tenant_id: str, external_provider: str | None, external_agent_id: str | None
    ) -> AnalyticsAgentView | None:
        agent = self._select_identity(tenant_id, external_provider, external_agent_id, lock=False)
        return agent_view(agent) if agent is not None else None

    def list_for_tenant(self, tenant_id: str) -> tuple[AnalyticsAgentView, ...]:
        rows = self.db.scalars(
            select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.created_at.desc())
        ).all()
        return tuple(agent_view(agent) for agent in rows)

    def create_agents(self, tenant_id: str, agents: Sequence[NewAgentCommand]) -> tuple[AnalyticsAgentView, ...]:
        """Plain inserts for tenant onboarding (a duplicate identity is an error); flush only."""
        created = []
        for command in agents:
            agent = Agent(
                tenant_id=tenant_id,
                name=command.name,
                external_provider=command.external_provider,
                external_agent_id=command.external_agent_id,
                channel_type=command.channel_type,
                status=command.status,
            )
            self.db.add(agent)
            self.db.flush()
            created.append(agent_view(agent))
        return tuple(created)

    def upsert_provider_agent(self, command: AgentUpsertCommand) -> AnalyticsAgentView:
        """Create-or-refresh by (tenant, provider, external agent); concurrent writers converge
        on one row through the unique constraint. Name/status refresh, channel only on create. Flush only."""
        agent = self._select_identity(command.tenant_id, command.external_provider, command.external_agent_id, lock=True)
        if agent is None:
            agent = Agent(
                tenant_id=command.tenant_id,
                external_provider=command.external_provider,
                external_agent_id=command.external_agent_id,
                name=command.name,
                channel_type=command.channel_type,
                status=command.status,
            )
            try:
                with self.db.begin_nested():
                    self.db.add(agent)
                    self.db.flush()
            except IntegrityError:
                agent = self._select_identity(
                    command.tenant_id, command.external_provider, command.external_agent_id, lock=True
                )
                if agent is None:
                    raise
        agent.name = command.name
        agent.status = command.status
        self.db.flush()
        return agent_view(agent)

    def resolve_unique_external_agent(
        self, external_agent_id: str, *, external_provider: str | None = None
    ) -> AnalyticsAgentView:
        """The one active agent with this provider id. Not tenant-scoped, so it fails closed on 0 or >1."""
        statement = select(Agent).where(Agent.external_agent_id == external_agent_id, Agent.status == "active")
        if external_provider is not None:
            statement = statement.where(Agent.external_provider == external_provider)
        matches = self.db.scalars(statement.limit(2)).all()
        if not matches:
            raise AnalyticsAgentNotFoundError("No active analytics agent matches the identifier")
        if len(matches) > 1:
            raise AmbiguousAnalyticsAgentError("The agent identifier matches more than one analytics agent")
        return agent_view(matches[0])

    def _select_identity(
        self, tenant_id: str, external_provider: str | None, external_agent_id: str | None, *, lock: bool
    ) -> Agent | None:
        statement = select(Agent).where(
            Agent.tenant_id == tenant_id,
            Agent.external_provider == external_provider,
            Agent.external_agent_id == external_agent_id,
        )
        return self.db.scalar(statement.with_for_update() if lock else statement)
