class BillingError(Exception):
    """Base for provider-neutral Billing errors."""


class BillingTenantNotFoundError(BillingError):
    pass


class InvalidBillingPlanError(BillingError, ValueError):
    pass


class MinutePackageExhaustedError(BillingError):
    pass


class TenantInactiveError(BillingError):
    pass


class BillingStateConflictError(BillingError):
    pass
