from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ExternalIdentity:
    external_auth_id: str
    email: str | None = None
    name: str | None = None
    email_verified: bool | None = None
    claims: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ProvisionedUser:
    external_auth_id: str
    connection: str | None = None
    created_via: str | None = None
    verification_email_sent: bool = False
    password_reset_triggered: bool = False
    activation_errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class LegacyAgentView:
    id: str
    tenant_id: str
    name: str
    external_provider: str | None
    external_agent_id: str | None
    channel_type: str | None
    status: str


@dataclass(frozen=True)
class PasswordResetOutcome:
    email: str
    ticket_url: str | None = field(default=None, repr=False)


class IdentityProvisioningPort(Protocol):
    """Provider-neutral account provisioning (Auth0 today). Pure contract: no provider types."""

    def provision_tenant_admin(self, *, email: str, name: str) -> ProvisionedUser: ...
    def delete_user(self, user_id: str) -> None: ...
    def send_verification_email(self, user_id: str) -> bool: ...
    def trigger_password_reset_email(self, *, email: str) -> bool: ...
    def create_password_change_ticket(self, *, email: str) -> str | None: ...
