"""Agent Builder -- public API.

Boundary only: TenantAgent/TenantAgentVersion still live in legacy
app.models.agents. Agent Builder owns them; other modules query them here.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agents import TenantAgentVersion


class AgentsFacade:
    def __init__(self, db: Session) -> None:
        self.db = db

    def is_tool_bound_to_published_version(self, tenant_id: str, tool_key: str) -> bool:
        published_versions = self.db.scalars(
            select(TenantAgentVersion).where(
                TenantAgentVersion.tenant_id == tenant_id, TenantAgentVersion.status == "published"
            )
        ).all()
        for version in published_versions:
            bindings = (version.runtime_binding_json or {}).get("tools", [])
            if any(isinstance(b, dict) and b.get("key") == tool_key for b in bindings):
                return True
        return False
