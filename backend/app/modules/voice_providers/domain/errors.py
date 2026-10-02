from __future__ import annotations


class VoiceProviderError(ValueError):
    """Provider-agnostic failure; ``code`` (== ``str(exc)``) is stable.

    ``remote`` is True when the provider itself rejected the request (as
    opposed to a local validation); ``reason`` is an optional, already
    allowlisted sub-reason (e.g. for a rejected voice preview)."""

    def __init__(self, code: str, *, remote: bool = False, reason: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.remote = remote
        self.reason = reason


class VoiceProviderNotAvailableError(VoiceProviderError):
    """Unknown provider, not active in the registry, or without an adapter."""

    def __init__(self, provider_key: str) -> None:
        super().__init__(f"Voice provider '{provider_key}' is not available.")
        self.provider_key = provider_key
