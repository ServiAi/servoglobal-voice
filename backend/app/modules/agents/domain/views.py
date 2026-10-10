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
class AgentLegacyBinding:
    tenant_id: str
    agent_id: str
    legacy_voice_agent_config_id: str
    agent_status: str


@dataclass(frozen=True, slots=True)
class AgentExperiencePublicationTarget:
    tenant_id: str
    agent_id: str
    agent_version_id: str
    legacy_voice_agent_config_id: str | None
    pipeline_type: str | None
    realtime_provider: str | None


@dataclass(frozen=True, slots=True)
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
class AgentEvaluationSnapshot:
    tenant_id: str
    agent_version_id: str
    agent_id: str
    version: int
    language: str
    name: str
    description: str | None
    role: str
    objective: str
    system_prompt: str
    greeting: str
    closing: str
    response_style: str
    interruptions: str
    turn_detection: str
    confirmation_strategy: str
    agent_first: bool
    enabled_tool_keys: tuple[str, ...]


class AgentEvaluationSnapshotUnavailableError(ValueError):
    def __init__(self, code: str = "historical_evidence_missing") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class AgentRuntimeTarget:
    """A tenant-verified, exact, executable agent version: provider-agnostic facts
    only (no runtime_binding_json, no ORM). ``version_status`` is ``published`` or
    ``superseded``; a draft version, or any version of a non-active agent, is never a target."""

    tenant_id: str
    agent_id: str
    agent_version_id: str
    version: int
    version_status: str
    pipeline_type: str | None
    realtime_provider: str | None

    @property
    def is_realtime(self) -> bool:
        return self.pipeline_type == "realtime" and self.realtime_provider is not None


class AgentRuntimeTargetUnavailableError(ValueError):
    """``code``: agent_version_not_found (also for another tenant's or another
    agent's version), agent_archived, agent_not_active (agent unpublished/draft),
    agent_version_not_executable (draft version)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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


class LegacyAgentBindingError(ValueError):
    """Stable failure code for resolving a legacy config to one Agent."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
