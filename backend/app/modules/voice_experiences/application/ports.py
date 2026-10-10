from __future__ import annotations

from typing import Protocol

from app.modules.voice_experiences.domain.views import LaunchSession, WebRTCJoin


class TurnstileVerificationPort(Protocol):
    async def verify(self, token: str | None, remote_ip: str) -> bool: ...


class VoiceRuntimePort(Protocol):
    """What the public WebRTC launch needs from the canonical voice runtime.
    Every method raises ``VoiceRuntimeUnavailable`` instead of leaking runtime internals."""

    def require_runnable_agent(self, tenant_id: str, agent_id: str, agent_version_id: str) -> str:
        """Provider of an exact, executable, realtime AgentVersion of an ACTIVE agent."""
        ...

    def validate_session_variables(self, variables: dict[str, object]) -> None:
        """Raises ``VoiceRuntimeUnavailable('invalid_context')`` when the runtime context
        contract (key count/length, size, secret-like keys) would reject ``variables``."""
        ...

    def create_exact_session(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        agent_version_id: str,
        idempotency_key: str,
        contact_id: str | None,
        lead_id: str | None,
        variables: dict[str, object],
    ) -> LaunchSession:
        """Idempotent per ``idempotency_key``: a retry returns the same session."""
        ...

    def attach_crm_call(self, session_id: str, tenant_id: str, crm_voice_call_id: str) -> None: ...

    async def ensure_webrtc_join(self, session_id: str, tenant_id: str) -> WebRTCJoin:
        """Dispatches the room once; replays only mint a new participant token."""
        ...
