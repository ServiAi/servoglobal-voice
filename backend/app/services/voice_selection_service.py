from __future__ import annotations

from app.domain.voice_registry import VoiceRegistryValidationError, validate_voice_compatibility
from app.schemas.agents import AgentVoiceConfig

_ELEVENLABS_SETTINGS_KEYS = {"model", "speed", "stability", "similarity_boost", "use_speaker_boost"}
_ELEVENLABS_SETTINGS_RANGES: dict[str, tuple[float, float]] = {
    "speed": (0.7, 1.2),
    "stability": (0.0, 1.0),
    "similarity_boost": (0.0, 1.0),
}
_ELEVENLABS_MODEL_MAX_LENGTH = 80


class VoiceSelectionError(ValueError):
    pass


class VoiceSelectionService:
    """Validates an AgentVoiceConfig against the realtime provider/model an
    agent is configured with, and against provider-specific settings rules.

    All provider-specific business logic (which settings keys/ranges a given
    (mode, provider) allows) lives here rather than on AgentVoiceConfig
    itself: the schema only knows shape, this service knows domain rules,
    and it's the single place to read or extend that logic (e.g. when a new
    external voice provider gets a real adapter).

    Phase A is local-only: static registry compatibility plus the settings
    checks below. No network or database I/O -- confirming that a specific
    voice_id actually exists/is accessible for a tenant is a publish-time
    preflight or an explicit preview action (later phases), never something
    draft save depends on.
    """

    def validate(self, runtime_provider: str, runtime_model: str, voice: AgentVoiceConfig) -> None:
        try:
            validate_voice_compatibility(runtime_provider, runtime_model, voice.mode, voice.provider)
        except VoiceRegistryValidationError as exc:
            raise VoiceSelectionError(str(exc)) from exc
        self.validate_settings(voice)

    @staticmethod
    def validate_settings(voice: AgentVoiceConfig) -> None:
        """The settings-shape half of `validate()`, exposed on its own for
        callers that have no realtime provider/model context to check
        registry compatibility against -- e.g. the standalone external-voice
        preview endpoint, which only ever needs to know whether `voice`'s own
        (mode, provider, settings) are internally well-formed."""
        if voice.mode == "provider":
            if voice.settings:
                raise VoiceSelectionError("Provider voice does not accept custom settings.")
            return
        if voice.mode == "provider_external" and voice.provider == "elevenlabs":
            settings = voice.settings
            unknown = set(settings) - _ELEVENLABS_SETTINGS_KEYS
            if unknown:
                raise VoiceSelectionError(f"Unsupported voice settings: {', '.join(sorted(unknown))}")
            for key, (low, high) in _ELEVENLABS_SETTINGS_RANGES.items():
                if key not in settings:
                    continue
                value = settings[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise VoiceSelectionError(f"Voice setting '{key}' must be a number.")
                if not low <= value <= high:
                    raise VoiceSelectionError(f"Voice setting '{key}' must be between {low} and {high}.")
            if "use_speaker_boost" in settings and not isinstance(settings["use_speaker_boost"], bool):
                raise VoiceSelectionError("Voice setting 'use_speaker_boost' must be a boolean.")
            if "model" in settings:
                model_value = settings["model"]
                if (
                    not isinstance(model_value, str)
                    or not model_value.strip()
                    or len(model_value) > _ELEVENLABS_MODEL_MAX_LENGTH
                ):
                    raise VoiceSelectionError("Voice setting 'model' must be a non-empty string.")
