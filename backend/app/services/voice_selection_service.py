from __future__ import annotations

from app.domain.voice_registry import VoiceRegistryValidationError, validate_voice_compatibility
from app.schemas.agents import AgentVoiceConfig


class VoiceSelectionError(ValueError):
    pass


class VoiceSelectionService:
    """Validates an AgentVoiceConfig against the realtime provider/model an
    agent is configured with.

    Phase A is local-only: static registry compatibility (validate below)
    plus the settings shape/allowlist/range checks AgentVoiceConfig already
    enforces on its own via Pydantic validators. No network or database I/O
    here -- confirming that a specific voice_id actually exists/is
    accessible for a tenant is a publish-time preflight or an explicit
    preview action (later phases), never something draft save depends on.
    """

    def validate(self, runtime_provider: str, runtime_model: str, voice: AgentVoiceConfig) -> None:
        try:
            validate_voice_compatibility(runtime_provider, runtime_model, voice.mode, voice.provider)
        except VoiceRegistryValidationError as exc:
            raise VoiceSelectionError(str(exc)) from exc
