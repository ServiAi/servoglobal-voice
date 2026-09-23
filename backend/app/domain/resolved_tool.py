from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.domain.tool_registry import ToolDefinition
from app.models.tools import TenantHttpToolConfig, TenantTool


@dataclass(frozen=True)
class ResolvedToolDefinition:
    """A single contract for both Platform Tools and Tenant Custom Tools.

    Not a Pydantic model: it never crosses a network boundary itself, it
    only feeds ToolCatalogService (-> AgentToolCatalogEntryResponse) and
    AgentCompilerService (-> CompiledToolSpec), both of which construct
    their own response explicitly field-by-field. `required_integration`
    is always None for source="custom" -- a custom tool's "is this tenant
    ready to run it" concept is credential-based, not this closed enum.
    """

    key: str
    name: str
    description: str
    status: Literal["available", "planned"]
    input_schema: dict[str, Any]
    source: Literal["platform", "custom"]
    required_integration: Literal["booking", "whatsapp", "crm", "chatwoot"] | None
    custom_tool_id: str | None = None


def from_platform(tool: ToolDefinition) -> ResolvedToolDefinition:
    return ResolvedToolDefinition(
        key=tool.key,
        name=tool.name,
        description=tool.description,
        status=tool.status,
        input_schema=tool.input_schema,
        source="platform",
        required_integration=tool.required_integration,
    )


def from_custom(tenant_tool: TenantTool, config: TenantHttpToolConfig) -> ResolvedToolDefinition:
    return ResolvedToolDefinition(
        key=tenant_tool.key,
        name=tenant_tool.name,
        description=tenant_tool.description,
        status="available" if tenant_tool.status == "active" else "planned",
        input_schema=config.input_schema_json,
        source="custom",
        required_integration=None,
        custom_tool_id=tenant_tool.id,
    )
