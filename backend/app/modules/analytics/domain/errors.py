class AnalyticsError(Exception):
    """Base class of Analytics failures (the API layer maps them to HTTP)."""


class AnalyticsTenantNotFoundError(AnalyticsError, LookupError):
    pass


class AnalyticsAgentNotFoundError(AnalyticsError, LookupError):
    pass


class AnalyticsAgentTenantMismatchError(AnalyticsError, ValueError):
    pass


class AmbiguousAnalyticsAgentError(AnalyticsError, LookupError):
    """More than one analytics agent matches an identifier that is not tenant-scoped."""


class CallNotFoundError(AnalyticsError, LookupError):
    pass


class InvalidDashboardFilterError(AnalyticsError, ValueError):
    pass


class AnalyticsConflictError(AnalyticsError):
    pass
