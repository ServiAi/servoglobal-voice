class IdentityError(Exception):
    """Base for provider-neutral Identity errors."""


class FeatureDisabledError(IdentityError):
    pass


class UnknownTenantFeatureError(IdentityError, ValueError):
    pass


class TenantFeatureTenantNotFoundError(IdentityError, LookupError):
    pass


class TenantDeletionBlockedError(IdentityError, RuntimeError):
    pass


class MembershipAlreadyExistsError(IdentityError, ValueError):
    pass


class ProvisioningConflictError(IdentityError):
    """The external identity already exists and needs account recovery."""

    status_code = 409


class IdentityProviderError(IdentityError):
    status_code = 502


class OnboardingConsistencyError(IdentityError, RuntimeError):
    def __init__(self, message: str, *, auth0_user_id: str, compensation_attempted: bool, compensation_succeeded: bool) -> None:
        super().__init__(message)
        self.auth0_user_id = auth0_user_id
        self.external_auth_id = auth0_user_id
        self.compensation_attempted = compensation_attempted
        self.compensation_succeeded = compensation_succeeded


# --- Authentication / authorization (the HTTP edge in identity.api.deps maps these to status codes) ---


class AuthenticationRequiredError(IdentityError):
    """No credentials were presented."""


class InvalidIdentityTokenError(IdentityError):
    """The token is invalid, expired, or lacks the required identity claims."""


class IdentityConfigurationError(IdentityError):
    """The identity provider integration is not configured on the backend."""


class EmailNotVerifiedError(IdentityError):
    pass


class UserInactiveError(IdentityError):
    pass


class UserNotRegisteredError(IdentityError):
    pass


class IdentityConflictError(IdentityError):
    """More than one internal user matches the external identity: manual resolution required."""


class MembershipRequiredError(IdentityError):
    """The authenticated user has no active tenant membership."""


class TenantNotFoundError(IdentityError, ValueError):
    """ValueError-compatible: administrative callers have always caught ValueError for this."""


class MembershipNotFoundError(IdentityError, LookupError):
    pass


class PasswordResetFailedError(IdentityProviderError):
    """The provider could not send the password email and no fallback ticket could be created."""
