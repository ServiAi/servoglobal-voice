from __future__ import annotations


class SchedulingProviderError(Exception):
    """Base exception for all scheduling provider operations."""


class SchedulingAuthenticationError(SchedulingProviderError):
    """Raised when authentication credentials (API key, OAuth token) are invalid or expired."""


class SchedulingPermissionError(SchedulingProviderError):
    """Raised when the connected account lacks permissions or the plan doesn't support the feature."""


class SchedulingNotFoundError(SchedulingProviderError):
    """Raised when the requested remote schedule, event type, team, or booking does not exist."""


class SchedulingConflictError(SchedulingProviderError):
    """Raised when a time slot conflict or duplicate resource exists."""


class SchedulingValidationError(SchedulingProviderError):
    """Raised when the payload or parameters fail upstream validation."""


class SchedulingFeatureUnsupportedError(SchedulingProviderError):
    """Raised when an operation is not supported by the provider."""


class SchedulingUpstreamError(SchedulingProviderError):
    """Raised when the provider API returns a 5xx or unexpected network/upstream failure."""
