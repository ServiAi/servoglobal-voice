from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from app.modules.analytics.public import (
    AnalyticsAgentDirectory,
    AnalyticsAgentView,
    AnalyticsMaintenance,
    NewAgentCommand,
)
from app.modules.identity.application.onboarding_service import OnboardingService
from app.modules.identity.domain.contracts import LegacyAgentView, ProvisionedUser
from app.modules.identity.domain.errors import (
    IdentityProviderError,
    ProvisioningConflictError,
)
from app.modules.identity.infrastructure.auth0.provisioning import (
    Auth0ProvisioningError,
    Auth0ProvisioningService,
)
from app.modules.identity.infrastructure.models import Tenant


class _ProvisioningAdapter:
    def __init__(self, service: Auth0ProvisioningService | None = None) -> None:
        self.service = service or Auth0ProvisioningService()

    def provision_tenant_admin(self, *, email: str, name: str) -> ProvisionedUser:
        try:
            result = self.service.provision_tenant_admin(email=email, name=name)
        except Auth0ProvisioningError as exc:
            if exc.status_code == 409:
                raise ProvisioningConflictError from exc
            raise IdentityProviderError("Identity provider provisioning failed") from exc
        return ProvisionedUser(
            external_auth_id=result.user_id,
            connection=result.connection,
            created_via=result.created_via,
            verification_email_sent=result.verification_email_sent,
            password_reset_triggered=result.password_reset_triggered,
            activation_errors=tuple(result.activation_errors or ()),
        )

    def delete_user(self, user_id: str) -> None:
        try:
            self.service.delete_user(user_id)
        except Auth0ProvisioningError as exc:
            raise IdentityProviderError("Identity provider deletion failed") from exc

    def send_verification_email(self, user_id: str) -> bool:
        try:
            return self.service.send_verification_email(user_id)
        except Auth0ProvisioningError as exc:
            raise IdentityProviderError("Identity provider verification failed") from exc

    def trigger_password_reset_email(self, *, email: str) -> bool:
        try:
            return self.service.trigger_password_reset_email(email=email)
        except Auth0ProvisioningError as exc:
            raise IdentityProviderError("Identity provider password reset failed") from exc

    def create_password_change_ticket(self, *, email: str) -> str | None:
        try:
            return self.service.create_password_change_ticket(email=email)
        except Auth0ProvisioningError as exc:
            raise IdentityProviderError("Identity provider ticket creation failed") from exc


def _agent_view(agent: AnalyticsAgentView) -> LegacyAgentView:
    return LegacyAgentView(
        id=agent.id,
        tenant_id=agent.tenant_id,
        name=agent.name,
        external_provider=agent.external_provider,
        external_agent_id=agent.external_agent_id,
        channel_type=agent.channel_type,
        status=agent.status,
    )


class _LegacyAgentAdapter:
    """Onboarding agents live in the Analytics agent projection (via analytics.public)."""

    def __init__(self, db: Session) -> None:
        self.directory = AnalyticsAgentDirectory(db)

    def create_agents(self, tenant_id: str, agents: Sequence[Mapping[str, object]]) -> tuple[LegacyAgentView, ...]:
        created = self.directory.create_agents(
            tenant_id,
            [
                NewAgentCommand(
                    name=str(values["name"]).strip(),
                    external_provider=str(values["external_provider"]).strip(),
                    external_agent_id=str(values["external_agent_id"]).strip(),
                    channel_type=values.get("channel_type"),
                    status=str(values.get("status", "active")),
                )
                for values in agents
            ],
        )
        return tuple(_agent_view(agent) for agent in created)

    def list_agents(self, tenant_id: str) -> tuple[LegacyAgentView, ...]:
        return tuple(_agent_view(agent) for agent in self.directory.list_for_tenant(tenant_id))


class _BillingAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_default_plan(self, tenant_id: str, plan: object | None) -> None:
        from app.modules.billing.public import BillingOnboardingFacade, BillingPlanInput

        billing_plan = (
            BillingPlanInput(
                plan_key=plan.plan_key,
                included_minutes=plan.included_minutes,
                price_per_minute_usd=plan.price_per_minute_usd,
            )
            if plan is not None
            else None
        )
        BillingOnboardingFacade(self.db).create_default_plan(tenant_id, billing_plan)

    def tenant_usage_snapshot(self, tenant_id: str) -> Mapping[str, object]:
        from dataclasses import asdict
        from datetime import datetime
        from decimal import Decimal

        from app.modules.billing.public import BillingOnboardingFacade

        def encode(value):
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, dict):
                return {key: encode(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(item) for item in value]
            return value

        return encode(asdict(BillingOnboardingFacade(self.db).tenant_usage_snapshot(tenant_id)))

    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]:
        from app.modules.billing.public import BillingOnboardingFacade

        return BillingOnboardingFacade(self.db).cleanup_tenant(tenant_id)


class _TenantDependentCleanupAdapter:
    def __init__(self, db: Session) -> None:
        self.maintenance = AnalyticsMaintenance(db)

    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]:
        return self.maintenance.cleanup_tenant(tenant_id)


def create_provisioning_adapter(
    service: Auth0ProvisioningService | None = None,
) -> _ProvisioningAdapter:
    return _ProvisioningAdapter(service)


def create_onboarding_service(
    db: Session, provisioning: Auth0ProvisioningService | _ProvisioningAdapter | None = None
) -> OnboardingService:
    return OnboardingService(
        db,
        provisioning=(provisioning if isinstance(provisioning, _ProvisioningAdapter) else _ProvisioningAdapter(provisioning)),
        billing=_BillingAdapter(db),
        legacy_agents=_LegacyAgentAdapter(db),
        tenant_cleanup=_TenantDependentCleanupAdapter(db),
    )
