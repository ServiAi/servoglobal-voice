from dataclasses import dataclass
from typing import Mapping


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
