from collections.abc import Mapping, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.billing import TenantBillingPlan, TenantUsageAlert
from app.modules.identity.application.onboarding_service import OnboardingService
from app.modules.identity.domain.contracts import LegacyAgentView, ProvisionedUser
from app.modules.identity.domain.errors import IdentityProviderError, ProvisioningConflictError
from app.modules.identity.infrastructure.auth0.provisioning import (
    Auth0ProvisioningError,
    Auth0ProvisioningService,
)
from app.modules.identity.infrastructure.models import Tenant
from app.services.tenant_usage_service import TenantUsageService


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


def _agent_view(agent: Agent) -> LegacyAgentView:
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
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_agents(self, tenant_id: str, agents: Sequence[Mapping[str, object]]) -> tuple[LegacyAgentView, ...]:
        result = []
        for values in agents:
            agent = Agent(
                tenant_id=tenant_id,
                name=str(values["name"]).strip(),
                external_provider=str(values["external_provider"]).strip(),
                external_agent_id=str(values["external_agent_id"]).strip(),
                channel_type=values.get("channel_type"),
                status=str(values.get("status", "active")),
            )
            self.db.add(agent)
            self.db.flush()
            result.append(_agent_view(agent))
        return tuple(result)

    def list_agents(self, tenant_id: str) -> tuple[LegacyAgentView, ...]:
        agents = self.db.scalars(
            select(Agent).where(Agent.tenant_id == tenant_id).order_by(Agent.created_at.desc())
        ).all()
        return tuple(_agent_view(agent) for agent in agents)

    def cleanup_tenant(self, tenant_id: str) -> int:
        result = self.db.execute(delete(Agent).where(Agent.tenant_id == tenant_id))
        return max(result.rowcount or 0, 0)


class _BillingAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.service = TenantUsageService(db)

    def create_default_plan(self, tenant_id: str, plan: object | None) -> None:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise LookupError(f"Tenant '{tenant_id}' not found")
        self.service.create_plan_for_tenant(tenant, plan, commit=False)

    def tenant_usage_snapshot(self, tenant_id: str) -> Mapping[str, object]:
        tenant = self.db.get(Tenant, tenant_id)
        if tenant is None:
            raise LookupError(f"Tenant '{tenant_id}' not found")
        return self.service.get_usage(tenant, persist_alerts=False).model_dump(mode="json")

    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]:
        alerts = self.db.execute(delete(TenantUsageAlert).where(TenantUsageAlert.tenant_id == tenant_id))
        plans = self.db.execute(delete(TenantBillingPlan).where(TenantBillingPlan.tenant_id == tenant_id))
        return {
            "usage_alerts": max(alerts.rowcount or 0, 0),
            "billing_plans": max(plans.rowcount or 0, 0),
        }


class _TenantDependentCleanupAdapter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def cleanup_tenant(self, tenant_id: str) -> Mapping[str, int]:
        counts: dict[str, int] = {}
        for name, model in (
            ("call_events", CallEvent),
            ("metric_snapshots", MetricSnapshotDaily),
            ("calls", Call),
        ):
            result = self.db.execute(delete(model).where(model.tenant_id == tenant_id))
            counts[name] = max(result.rowcount or 0, 0)
        return counts


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
