"""Tool Platform -- public API.

The only import path other modules may use for tools. Everything under
app.modules.tools.{domain,application,infrastructure,api} is internal and
may change without notice (enforced by test_module_boundaries.py).

Consumers today:
- Agent Builder: catalog, binding validation, compile-time resolution.
- Voice Orchestration (runtime endpoint): live tool invocation.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.tools.application.catalog import ToolCatalogService
from app.modules.tools.application.contracts import (
    PlatformToolContractError,
    PlatformToolContractService,
)
from app.modules.tools.application.dispatcher import ToolDispatchService
from app.modules.tools.application.resolver import ToolResolverService
from app.modules.tools.domain.errors import (
    ToolArgumentError,
    ToolDispatchError,
    ToolExecutionError,
    ToolNotAvailableError,
    ToolNotFoundError,
)
from app.modules.tools.domain.registry import ToolRegistryValidationError, get_tool
from app.modules.tools.domain.resolved_tool import ResolvedToolDefinition, from_platform
from app.modules.tools.infrastructure.credentials import TenantToolCredentialService

__all__ = [
    "PlatformToolContractError",
    "PlatformToolContractService",
    "ResolvedToolDefinition",
    "ToolArgumentError",
    "ToolCatalogService",
    "ToolDispatchError",
    "ToolDispatchService",
    "ToolExecutionError",
    "ToolNotAvailableError",
    "ToolNotFoundError",
    "ToolRegistryValidationError",
    "ToolResolverService",
    "from_platform",
    "get_tool",
    "is_custom_tool_credential_ready",
]


def is_custom_tool_credential_ready(db: Session, tenant_id: str, custom_tool_id: str) -> bool:
    """Presence check only. The credential service itself (which can
    decrypt secrets) is deliberately not part of the public API."""
    return TenantToolCredentialService(db).is_configured_or_not_required(tenant_id, custom_tool_id)
