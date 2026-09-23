from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.resolved_tool import ResolvedToolDefinition, from_custom, from_platform
from app.domain.tool_registry import get_tool, list_tools
from app.models.tools import TenantHttpToolConfig, TenantTool
from app.services.tenant_feature_service import CUSTOM_HTTP_TOOLS, TenantFeatureService


class ToolResolverService:
    """Single seam that merges the static platform Tool Registry with the
    DB-backed, per-tenant Custom HTTP Tools catalog into one contract
    (ResolvedToolDefinition). AgentService, AgentCompilerService and
    ToolDispatchService all resolve tool keys through this service instead
    of each re-implementing the platform-vs-custom branch.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(self, tenant_id: str, key: str) -> ResolvedToolDefinition | None:
        if key.startswith("custom."):
            row = self.get_active_custom_tool(tenant_id, key)
            if row is None:
                return None
            tenant_tool, config = row
            return from_custom(tenant_tool, config)
        tool = get_tool(key)
        return from_platform(tool) if tool is not None else None

    def list_all(
        self, tenant_id: str, *, status: str | None = None
    ) -> list[ResolvedToolDefinition]:
        resolved = [from_platform(tool) for tool in list_tools(status=status)]
        if status == "planned":
            # Active custom tools are only ever "available"; disabled custom
            # tools are never surfaced through this catalog-merge path (the
            # tenant's own CRUD listing shows their real status directly).
            return resolved
        for tenant_tool, config in self._list_active_custom_tools(tenant_id):
            resolved.append(from_custom(tenant_tool, config))
        return resolved

    def get_active_custom_tool(
        self, tenant_id: str, key: str
    ) -> tuple[TenantTool, TenantHttpToolConfig] | None:
        """Exposes the raw ORM rows (not just the compiled contract) --
        CustomHttpToolExecutor needs the actual HTTP config to run, which
        ResolvedToolDefinition deliberately never carries."""
        if not TenantFeatureService(self.db).is_enabled(tenant_id, CUSTOM_HTTP_TOOLS):
            return None
        row = self.db.execute(
            select(TenantTool, TenantHttpToolConfig)
            .join(TenantHttpToolConfig, TenantHttpToolConfig.tenant_tool_id == TenantTool.id)
            .where(
                TenantTool.tenant_id == tenant_id,
                TenantTool.key == key,
                TenantTool.status == "active",
            )
        ).first()
        return (row[0], row[1]) if row is not None else None

    def _list_active_custom_tools(
        self, tenant_id: str
    ) -> list[tuple[TenantTool, TenantHttpToolConfig]]:
        if not TenantFeatureService(self.db).is_enabled(tenant_id, CUSTOM_HTTP_TOOLS):
            return []
        rows = self.db.execute(
            select(TenantTool, TenantHttpToolConfig)
            .join(TenantHttpToolConfig, TenantHttpToolConfig.tenant_tool_id == TenantTool.id)
            .where(TenantTool.tenant_id == tenant_id, TenantTool.status == "active")
        ).all()
        return [(row[0], row[1]) for row in rows]
