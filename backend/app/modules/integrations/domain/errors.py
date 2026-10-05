"""Provider-neutral errors. Infrastructure adapters raise subclasses of these;
application code only ever catches the neutral types."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for every failure reported by an external provider."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached or timed out."""


class ProviderRejected(ProviderError):
    """The provider answered and refused the request."""


class ProviderConfigurationError(ProviderError):
    """The tenant's provider configuration is missing or unusable."""


class ProviderOutcomeUnknown(ProviderError):
    """The provider may or may not have performed the action; never retry blindly."""
