from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class VoiceProvider:
    key: str
    name: str
    status: Literal["active", "planned"]
    supports_managed_credentials: bool
    supports_byok: bool


@dataclass(frozen=True)
class ParameterSpec:
    supported: bool
    min: float | None = None
    max: float | None = None
    default: Any = None


@dataclass(frozen=True)
class VoiceModel:
    id: str
    provider_key: str
    key: str
    name: str
    model_type: Literal["stt", "llm", "tts", "realtime"]
    implementation_status: Literal["planned", "available", "deprecated"]
    capabilities: dict[str, bool] = field(default_factory=dict)
    parameters: dict[str, ParameterSpec] = field(default_factory=dict)


class VoiceRegistryValidationError(ValueError):
    pass


# Platform-managed catalog. Adding a provider or model here without a real
# adapter is exactly the "fingir soporte funcional" this registry exists to
# prevent -- new rows land only alongside the code that can actually execute
# them. Editing this requires a deploy by design (see AGENT_BUILDER_ARCHITECTURE.md).
_PROVIDERS: tuple[VoiceProvider, ...] = (
    VoiceProvider(
        key="ultravox",
        name="Ultravox",
        status="active",
        supports_managed_credentials=False,
        supports_byok=True,
    ),
    VoiceProvider(key="openai", name="OpenAI", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="google", name="Google", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="aws", name="AWS", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="deepgram", name="Deepgram", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="cartesia", name="Cartesia", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="elevenlabs", name="ElevenLabs", status="planned", supports_managed_credentials=False, supports_byok=False),
    VoiceProvider(key="anthropic", name="Anthropic", status="planned", supports_managed_credentials=False, supports_byok=False),
)

_MODELS: tuple[VoiceModel, ...] = (
    VoiceModel(
        id="ultravox:ultravox",
        provider_key="ultravox",
        key="ultravox",
        name="Ultravox Realtime",
        model_type="realtime",
        implementation_status="available",
        capabilities={
            "tools": True,
            "voice_selection": True,
            "turn_detection": True,
            "interruptions": True,
            "transcription": True,
            "function_calling": True,
            "reasoning": False,
        },
        parameters={
            "temperature": ParameterSpec(supported=False),
        },
    ),
)

_PROVIDERS_BY_KEY = {provider.key: provider for provider in _PROVIDERS}
_MODELS_BY_ID = {model.id: model for model in _MODELS}


def list_providers() -> list[VoiceProvider]:
    return list(_PROVIDERS)


def list_models(
    *, model_type: str | None = None, provider_key: str | None = None, status: str | None = None
) -> list[VoiceModel]:
    models = _MODELS
    if model_type is not None:
        models = tuple(m for m in models if m.model_type == model_type)
    if provider_key is not None:
        models = tuple(m for m in models if m.provider_key == provider_key)
    if status is not None:
        models = tuple(m for m in models if m.implementation_status == status)
    return list(models)


def get_model(model_id: str) -> VoiceModel | None:
    return _MODELS_BY_ID.get(model_id)


def get_provider(provider_key: str) -> VoiceProvider | None:
    return _PROVIDERS_BY_KEY.get(provider_key)


def validate_runtime_selection(pipeline_type: str, provider_key: str, model_key: str) -> None:
    if pipeline_type != "realtime":
        raise VoiceRegistryValidationError(
            f"Unsupported pipeline_type '{pipeline_type}'. Only 'realtime' is available today."
        )
    provider = get_provider(provider_key)
    if provider is None or provider.status != "active":
        raise VoiceRegistryValidationError(f"Provider '{provider_key}' is not available.")
    model = get_model(f"{provider_key}:{model_key}")
    if (
        model is None
        or model.model_type != "realtime"
        or model.implementation_status != "available"
    ):
        raise VoiceRegistryValidationError(
            f"Model '{model_key}' is not available for provider '{provider_key}'."
        )
