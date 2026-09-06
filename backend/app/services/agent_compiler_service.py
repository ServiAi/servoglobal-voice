from __future__ import annotations

from app.models.agents import TenantAgent, TenantAgentVersion


def compile_runtime_session_spec(agent: TenantAgent, version: TenantAgentVersion) -> dict:
    """Compile an Agent + AgentVersion into a provider-agnostic RuntimeSessionSpec.

    This is the first step of the future AgentCompiler (identity + behavior +
    runtime binding -> RuntimeSessionSpec -> provider runtime). It does not
    resolve secrets or call any provider; that stays the job of the runtime
    adapter (see `agent_runtime_adapter.py`).
    """

    return {
        "agent_id": agent.id,
        "agent_version_id": version.id,
        "tenant_id": agent.tenant_id,
        "instructions": version.instructions_json,
        "behavior": version.behavior_json,
        "language": version.language,
        "timezone": version.timezone,
        "pipeline": version.runtime_binding_json,
    }
