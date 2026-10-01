"""Frozen views Agent Builder hands to other modules -- never ORM rows.

Parsing runtime_binding_json["tools"] is Agent Builder's job; other
modules only see AgentToolBindingView (Tool Platform owns ``config``)."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class AgentToolBindingView:
    key: str
    enabled: bool
    config: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def tool_binding_views(runtime_binding_json: Any) -> tuple[AgentToolBindingView, ...]:
    raw = runtime_binding_json.get("tools", []) if isinstance(runtime_binding_json, dict) else []
    views = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        config = item.get("config")
        views.append(
            AgentToolBindingView(
                key=item["key"],
                enabled=bool(item.get("enabled", True)),
                config=MappingProxyType(deepcopy(config) if isinstance(config, dict) else {}),
            )
        )
    return tuple(views)


@dataclass(frozen=True)
class PublishedAgent:
    agent_id: str
    tenant_id: str
    version_id: str
    pipeline_type: str | None
    realtime_provider: str | None

    @property
    def is_realtime(self) -> bool:
        return self.pipeline_type == "realtime" and self.realtime_provider is not None


@dataclass(frozen=True)
class AgentDisplay:
    """What history/projections show for an agent, deleted or not."""

    name: str | None
    status: str | None


@dataclass(frozen=True)
class ImportedAgent:
    agent_id: str
    draft_version_id: str
    warnings: tuple[str, ...]


class PublishedAgentUnavailableError(ValueError):
    """``code`` is ``agent_not_active`` or ``published_version_invalid``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
