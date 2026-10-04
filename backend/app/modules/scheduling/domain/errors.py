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


# --------------------------------------------------------------------------
# Neutral errors raised across the module boundary. They subclass ValueError
# on purpose: every HTTP adapter already maps ValueError (messages and status
# codes are part of the external contract) and callers never see Google,
# Cal.com or SQLAlchemy exceptions.
# --------------------------------------------------------------------------
class SchedulingError(ValueError):
    """Base class for Scheduling business errors."""


class BookingNotFoundError(SchedulingError):
    def __init__(self, message: str = "Booking not found") -> None:
        super().__init__(message)


class BookingCustomerNotFoundError(SchedulingError):
    def __init__(self, message: str = "Lead not found") -> None:
        super().__init__(message)


class SchedulingConfigurationError(SchedulingError):
    """No usable booking provider/config for the tenant."""


class AvailabilityError(SchedulingError):
    """Availability could not be computed (invalid input or provider failure)."""


class GoogleConnectionNotFoundError(SchedulingError):
    def __init__(self, message: str = "Google Calendar connection not found.") -> None:
        super().__init__(message)


class SlotConflictError(SchedulingError):
    """The resource already has an active booking overlapping the interval."""

    def __init__(self, message: str = "The requested time slot is no longer available.") -> None:
        super().__init__(message)


class IdempotencyConflictError(SchedulingError):
    """The same idempotency key was reused for a different request."""

    def __init__(self, message: str = "Idempotency key was already used with a different request.") -> None:
        super().__init__(message)


class BookingOperationInProgressError(SchedulingError):
    """An operation with this key is running or its provider outcome is
    uncertain. The provider is NOT called again; retry later or reconcile."""

    def __init__(self, message: str = "A booking operation with this key is still in progress.") -> None:
        super().__init__(message)
