from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.tool_resolver_service import ToolResolverService


class ToolCatalogService:
    """Builds the unified (platform + custom) catalog backing
    GET /api/v1/agents/tools/catalog. Response dicts are built explicitly
    field-by-field so a custom tool's HTTP config/credential can never leak
    into the catalog, even by accident.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.resolver = ToolResolverService(db)

    def build_catalog(self, tenant_id: str, *, is_available: callable) -> list[dict[str, Any]]:
        """`is_available(resolved) -> bool` is injected by the caller
        (AgentService) since integration-configured checks for platform
        tools need tenant-scoped service calls this module shouldn't own.
        """
        entries = []
        for resolved in self.resolver.list_all(tenant_id):
            entries.append(
                {
                    "key": resolved.key,
                    "name": resolved.name,
                    "description": resolved.description,
                    "status": resolved.status,
                    "required_integration": resolved.required_integration,
                    "available": resolved.status == "available" and is_available(resolved),
                    "input_schema": resolved.input_schema,
                    "source": resolved.source,
                    "context_requirements": [
                        {"path": req.path, "required": req.required, "description": req.description}
                        for req in resolved.context_requirements
                    ],
                    "binding_config_schema": resolved.binding_config_schema,
                    "configuration_required": bool(resolved.binding_config_schema),
                }
            )
        return entries
