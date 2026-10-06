from collections.abc import Mapping, Sequence
from typing import Protocol

from app.modules.identity.domain.contracts import (  # noqa: F401  (re-exported contract)
    ExternalIdentity,
    IdentityProvisioningPort,
    ProvisionedUser,
)


class IdentityTokenVerifierPort(Protocol):
    def verify(self, token: str) -> ExternalIdentity: ...


class BillingOnboardingPort(Protocol):
    def create_default_plan(self, tenant_id: str, plan: object | None) -> None: ...
    def tenant_usage_snapshot(self, tenant_id: str) -> Mapping[str, object]: ...
    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]: ...


class LegacyAgentAdministrationPort(Protocol):
    def create_agents(self, tenant_id: str, agents: Sequence[Mapping[str, object]]) -> Sequence[object]: ...
    def list_agents(self, tenant_id: str) -> Sequence[object]: ...


class TenantDependentCleanupPort(Protocol):
    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]: ...
