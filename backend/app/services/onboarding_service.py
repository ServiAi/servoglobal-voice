from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.services.auth0_provisioning_service import (
    Auth0ProvisionedUser,
    Auth0ProvisioningError,
    Auth0ProvisioningService,
)


class OnboardingConsistencyError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        auth0_user_id: str,
        compensation_attempted: bool,
        compensation_succeeded: bool,
    ) -> None:
        super().__init__(message)
        self.auth0_user_id = auth0_user_id
        self.compensation_attempted = compensation_attempted
        self.compensation_succeeded = compensation_succeeded


class TenantDeletionBlockedError(RuntimeError):
    pass


class OnboardingService:
    def __init__(
        self,
        db: Session,
        auth0_provisioning_service: Auth0ProvisioningService | None = None,
    ) -> None:
        self.db = db
        self.auth0_provisioning_service = (
            auth0_provisioning_service or Auth0ProvisioningService()
        )

    def create_tenant(
        self,
        *,
        name: str,
        slug: str,
        timezone: str = "America/Bogota",
        status: str = "active",
        admin_name: str,
        admin_email: str,
        admin_role: str = "tenant_admin",
        agents: list[dict] | None = None,
    ) -> dict:
        slug = slug.strip().lower()
        normalized_admin_email = admin_email.strip().lower()

        existing_tenant = self.db.scalar(
            select(Tenant).where(Tenant.slug == slug)
        )
        if existing_tenant is not None:
            raise ValueError(f"Tenant slug '{slug}' already exists")

        existing_user = self._get_existing_active_user_by_email(normalized_admin_email)
        if existing_user is not None and existing_user.external_auth_id is not None:
            raise ValueError(f"A user with external_auth_id already exists for email '{admin_email}'")

        provisioned_admin = self.auth0_provisioning_service.provision_tenant_admin(
            email=normalized_admin_email,
            name=admin_name.strip(),
        )

        try:
            tenant = Tenant(
                name=name.strip(),
                slug=slug,
                timezone=timezone,
                status=status,
            )
            self.db.add(tenant)
            self.db.flush()

            if existing_user is None:
                admin_user = User(
                    external_auth_id=provisioned_admin.user_id,
                    email=normalized_admin_email,
                    name=admin_name.strip(),
                    is_internal=False,
                    status="active",
                )
                self.db.add(admin_user)
                self.db.flush()
            else:
                admin_user = existing_user
                admin_user.external_auth_id = provisioned_admin.user_id
                admin_user.name = admin_name.strip()
                admin_user.status = "active"

            membership = TenantMembership(
                tenant_id=tenant.id,
                user_id=admin_user.id,
                role=admin_role.strip(),
                status="active",
            )
            self.db.add(membership)
            self.db.flush()

            agent_list = []
            if agents:
                for agent_data in agents:
                    agent = Agent(
                        tenant_id=tenant.id,
                        name=agent_data["name"].strip(),
                        external_provider=agent_data["external_provider"].strip(),
                        external_agent_id=agent_data["external_agent_id"].strip(),
                        channel_type=agent_data.get("channel_type"),
                        status=agent_data.get("status", "active"),
                    )
                    self.db.add(agent)
                    agent_list.append(agent)
                self.db.flush()

            self.db.commit()
            self.db.refresh(tenant)
            self.db.refresh(admin_user)
            self.db.refresh(membership)

            for a in agent_list:
                self.db.refresh(a)

            return self._build_tenant_response(
                tenant,
                admin_user,
                membership,
                agent_list,
                auth0_provisioning=provisioned_admin,
            )
        except Exception as exc:
            self.db.rollback()
            try:
                self.auth0_provisioning_service.delete_user(provisioned_admin.user_id)
            except Auth0ProvisioningError as cleanup_exc:
                raise OnboardingConsistencyError(
                    "Tenant local creation failed after Auth0 user creation; "
                    f"Auth0 cleanup failed: {cleanup_exc}",
                    auth0_user_id=provisioned_admin.user_id,
                    compensation_attempted=True,
                    compensation_succeeded=False,
                ) from exc
            raise OnboardingConsistencyError(
                "Tenant local creation failed after Auth0 user creation; "
                "Auth0 user was deleted",
                auth0_user_id=provisioned_admin.user_id,
                compensation_attempted=True,
                compensation_succeeded=True,
            ) from exc

    def list_tenants(self) -> list[Tenant]:
        return list(
            self.db.query(Tenant)
            .order_by(Tenant.created_at.desc())
            .all()
        )

    def get_tenant(self, tenant_id: str) -> Tenant:
        tenant = self.db.scalar(
            select(Tenant)
            .options(
                joinedload(Tenant.memberships),
                joinedload(Tenant.agents),
            )
            .where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")
        return tenant

    def update_tenant(
        self,
        tenant_id: str,
        *,
        name: str | None = None,
        timezone: str | None = None,
        status: str | None = None,
    ) -> Tenant:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        if name is not None:
            tenant.name = name.strip()
        if timezone is not None:
            tenant.timezone = timezone
        if status is not None:
            tenant.status = status

        self.db.commit()
        self.db.refresh(tenant)
        return tenant

    def delete_tenant(self, tenant_id: str) -> dict:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        self._ensure_tenant_can_be_deleted(tenant)

        tenant_slug = tenant.slug
        deleted_auth0_users = 0
        deleted_users = 0
        try:
            deleted_call_events = self._delete_count(
                delete(CallEvent).where(CallEvent.tenant_id == tenant_id)
            )
            deleted_metric_snapshots = self._delete_count(
                delete(MetricSnapshotDaily).where(
                    MetricSnapshotDaily.tenant_id == tenant_id
                )
            )
            deleted_calls = self._delete_count(
                delete(Call).where(Call.tenant_id == tenant_id)
            )
            deleted_agents = self._delete_count(
                delete(Agent).where(Agent.tenant_id == tenant_id)
            )
            memberships = self.db.scalars(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id
                )
            ).all()
            membership_user_ids = list(dict.fromkeys(m.user_id for m in memberships))
            deleted_memberships = self._delete_count(
                delete(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id
                )
            )
            deleted_audit_logs = self._delete_count(
                delete(AccessAuditLog).where(AccessAuditLog.tenant_id == tenant_id)
            )

            for user_id in membership_user_ids:
                user = self.db.scalar(select(User).where(User.id == user_id))
                if user:
                    if user.external_auth_id:
                        try:
                            self.auth0_provisioning_service.delete_user(
                                user.external_auth_id
                            )
                            deleted_auth0_users += 1
                        except Auth0ProvisioningError:
                            pass

                    self.db.delete(user)
                    deleted_users += 1

            self.db.delete(tenant)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return {
            "id": tenant_id,
            "slug": tenant_slug,
            "deleted": True,
            "deleted_counts": {
                "call_events": deleted_call_events,
                "metric_snapshots": deleted_metric_snapshots,
                "calls": deleted_calls,
                "agents": deleted_agents,
                "memberships": deleted_memberships,
                "access_audit_logs": deleted_audit_logs,
                "tenants": 1,
                "users": deleted_users,
                "auth0_users": deleted_auth0_users,
            },
        }

    def add_membership(
        self,
        tenant_id: str,
        *,
        email: str,
        role: str = "tenant_analyst",
    ) -> TenantMembership:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        user = self.db.scalar(
            select(User).where(User.email == email.strip().lower())
        )
        if user is None:
            raise ValueError(f"User with email '{email}' not found")

        existing = self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if existing is not None:
            raise ValueError(f"User '{email}' already has a membership in this tenant")

        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role.strip(),
            status="active",
        )
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)
        return membership

    def list_memberships(self, tenant_id: str) -> list[TenantMembership]:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        return list(
            self.db.query(TenantMembership)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.created_at.desc())
            .all()
        )

    def add_agent(
        self,
        tenant_id: str,
        *,
        name: str,
        external_provider: str,
        external_agent_id: str,
        channel_type: str | None = None,
        status: str = "active",
    ) -> Agent:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        agent = Agent(
            tenant_id=tenant.id,
            name=name.strip(),
            external_provider=external_provider.strip(),
            external_agent_id=external_agent_id.strip(),
            channel_type=channel_type,
            status=status,
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def list_agents(self, tenant_id: str) -> list[Agent]:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise ValueError(f"Tenant '{tenant_id}' not found")

        return list(
            self.db.query(Agent)
            .where(Agent.tenant_id == tenant_id)
            .order_by(Agent.created_at.desc())
            .all()
        )

    def _build_tenant_response(
        self,
        tenant: Tenant,
        admin_user: User,
        membership: TenantMembership,
        agents: list[Agent],
        *,
        auth0_provisioning: Auth0ProvisionedUser | None = None,
    ) -> dict:
        member_dicts = [
            {
                "id": m.id,
                "tenant_id": m.tenant_id,
                "user_id": m.user_id,
                "role": m.role,
                "status": m.status,
                "user_email": m.user.email if m.user else None,
                "user_name": m.user.name if m.user else None,
            }
            for m in tenant.memberships
        ]

        agent_dicts = [
            {
                "id": a.id,
                "tenant_id": a.tenant_id,
                "name": a.name,
                "external_provider": a.external_provider,
                "external_agent_id": a.external_agent_id,
                "channel_type": a.channel_type,
                "status": a.status,
            }
            for a in agents
        ]

        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "timezone": tenant.timezone,
            "status": tenant.status,
            "admin": {
                "id": admin_user.id,
                "name": admin_user.name,
                "email": admin_user.email,
                "is_internal": admin_user.is_internal,
                "external_auth_id": admin_user.external_auth_id,
                "has_auth0_link": admin_user.external_auth_id is not None,
                "auth0_provisioning": {
                    "user_created": auth0_provisioning is not None,
                    "user_id": admin_user.external_auth_id,
                    "connection": (
                        auth0_provisioning.connection
                        if auth0_provisioning is not None
                        else None
                    ),
                    "created_via": (
                        auth0_provisioning.created_via
                        if auth0_provisioning is not None
                        else None
                    ),
                    "verification_email_sent": (
                        auth0_provisioning.verification_email_sent
                        if auth0_provisioning is not None
                        else False
                    ),
                    "password_reset_triggered": (
                        auth0_provisioning.password_reset_triggered
                        if auth0_provisioning is not None
                        else False
                    ),
                    "activation_errors": (
                        auth0_provisioning.activation_errors
                        if auth0_provisioning is not None
                        else []
                    ),
                },
            },
            "memberships": member_dicts,
            "agents": agent_dicts,
            "is_ready_for_calls": len(agent_dicts) > 0,
        }

    def _get_existing_active_user_by_email(self, email: str) -> User | None:
        return self.db.scalar(
            select(User).where(
                User.email == email,
                User.status != "deleted",
            )
        )

    def _ensure_tenant_can_be_deleted(self, tenant: Tenant) -> None:
        internal_membership = self.db.scalar(
            select(TenantMembership)
            .join(User)
            .where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.status == "active",
                User.is_internal.is_(True),
            )
        )
        if internal_membership is not None:
            raise TenantDeletionBlockedError(
                "Tenant cannot be deleted while it has active internal user memberships"
            )

    def _delete_count(self, statement) -> int:
        result = self.db.execute(statement)
        return max(result.rowcount or 0, 0)
