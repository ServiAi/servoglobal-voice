from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.modules.identity.application.ports import (
    BillingOnboardingPort,
    IdentityProvisioningPort,
    LegacyAgentAdministrationPort,
    TenantDependentCleanupPort,
)
from app.modules.identity.domain.contracts import LegacyAgentView, PasswordResetOutcome, ProvisionedUser
from app.modules.identity.domain.errors import (
    IdentityProviderError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    OnboardingConsistencyError,
    PasswordResetFailedError,
    ProvisioningConflictError,
    TenantDeletionBlockedError,
    TenantNotFoundError,
)
from app.modules.identity.domain.roles import ADMIN_ROLES
from app.modules.identity.infrastructure.models import AccessAuditLog, Tenant, TenantMembership, User

logger = logging.getLogger(__name__)






class OnboardingService:
    def __init__(
        self,
        db: Session,
        *,
        provisioning: IdentityProvisioningPort,
        billing: BillingOnboardingPort,
        legacy_agents: LegacyAgentAdministrationPort,
        tenant_cleanup: TenantDependentCleanupPort,
    ) -> None:
        self.db = db
        self.provisioning = provisioning
        self.billing = billing
        self.legacy_agents = legacy_agents
        self.tenant_cleanup = tenant_cleanup

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
        plan: object | None = None,
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

        provisioned_admin = self.provisioning.provision_tenant_admin(
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
            self.billing.create_default_plan(tenant.id, plan)

            if existing_user is None:
                admin_user = User(
                    external_auth_id=provisioned_admin.external_auth_id,
                    email=normalized_admin_email,
                    name=admin_name.strip(),
                    is_internal=False,
                    status="active",
                )
                self.db.add(admin_user)
                self.db.flush()
            else:
                admin_user = existing_user
                admin_user.external_auth_id = provisioned_admin.external_auth_id
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

            agent_list = self.legacy_agents.create_agents(tenant.id, agents or ())

            self.db.commit()
            self.db.refresh(tenant)
            self.db.refresh(admin_user)
            self.db.refresh(membership)

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
                self.provisioning.delete_user(provisioned_admin.external_auth_id)
            except Exception:
                raise OnboardingConsistencyError(
                    "Tenant local creation failed after Auth0 user creation; "
                    "identity provider cleanup failed",
                    auth0_user_id=provisioned_admin.external_auth_id,
                    compensation_attempted=True,
                    compensation_succeeded=False,
                ) from exc
            raise OnboardingConsistencyError(
                "Tenant local creation failed after Auth0 user creation; "
                "Auth0 user was deleted",
                auth0_user_id=provisioned_admin.external_auth_id,
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
            )
            .where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")
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
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")

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
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")

        self._ensure_tenant_can_be_deleted(tenant)

        tenant_slug = tenant.slug
        deleted_auth0_users = 0
        deleted_users = 0
        try:
            memberships = self.db.scalars(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id
                )
            ).all()
            membership_user_ids = list(dict.fromkeys(m.user_id for m in memberships))
            tenant_users = [
                user
                for user in (
                    self.db.scalar(select(User).where(User.id == user_id))
                    for user_id in membership_user_ids
                )
                if user is not None
            ]
            shared_user_ids = set(
                self.db.scalars(
                    select(TenantMembership.user_id).where(
                        TenantMembership.user_id.in_(membership_user_ids),
                        TenantMembership.tenant_id != tenant_id,
                    )
                ).all()
            ) if membership_user_ids else set()
            users_to_delete = [user for user in tenant_users if user.id not in shared_user_ids]
            for user in users_to_delete:
                if user.external_auth_id:
                    self.provisioning.delete_user(
                        user.external_auth_id
                    )
                    deleted_auth0_users += 1

            tenant_cleanup_counts = self.tenant_cleanup.cleanup_tenant(tenant_id)
            billing_cleanup_counts = self.billing.cleanup_tenant(tenant_id)
            deleted_agents = self.legacy_agents.cleanup_tenant(tenant_id)
            deleted_call_events = tenant_cleanup_counts.get("call_events", 0)
            deleted_metric_snapshots = tenant_cleanup_counts.get("metric_snapshots", 0)
            deleted_calls = tenant_cleanup_counts.get("calls", 0)
            deleted_usage_alerts = billing_cleanup_counts.get("usage_alerts", 0)
            deleted_billing_plans = billing_cleanup_counts.get("billing_plans", 0)
            deleted_memberships = self._delete_count(
                delete(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id
                )
            )
            deleted_audit_logs = self._delete_count(
                delete(AccessAuditLog).where(AccessAuditLog.tenant_id == tenant_id)
            )

            for user in users_to_delete:
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
                "usage_alerts": deleted_usage_alerts,
                "billing_plans": deleted_billing_plans,
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
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")

        normalized_email = email.strip().lower()
        user = self.db.scalar(
            select(User).where(User.email == normalized_email)
        )
        ticket_url: str | None = None

        if user is None:
            user_name = normalized_email.split("@")[0]
            external_auth_id: str | None = None
            try:
                provisioned = self.provisioning.provision_tenant_admin(
                    email=normalized_email,
                    name=user_name,
                )
                external_auth_id = provisioned.external_auth_id
            except ProvisioningConflictError as exc:
                if exc.status_code == 409:
                    # User already exists in Auth0; trigger password reset directly
                    try:
                        self.provisioning.trigger_password_reset_email(
                            email=normalized_email
                        )
                    except Exception as reset_exc:
                        logger.warning("Failed triggering Auth0 password reset on 409: %s", reset_exc)
                else:
                    logger.warning("Auth0 provisioning error when adding member: %s", exc)
            except Exception as exc:
                logger.warning("Unexpected error provisioning user in Auth0: %s", exc)

            try:
                ticket_url = self.provisioning.create_password_change_ticket(
                    email=normalized_email
                )
            except Exception as exc:
                logger.warning("Could not create password ticket for new user: %s", exc)

            user = User(
                email=normalized_email,
                name=user_name,
                external_auth_id=external_auth_id,
                is_internal=False,
                status="active",
            )
            self.db.add(user)
            from sqlalchemy.exc import IntegrityError

            try:
                self.db.flush()
            except IntegrityError:
                self.db.rollback()
                user = self.db.scalar(
                    select(User).where(User.email == normalized_email)
                )
                if user is None:
                    raise
        else:
            if user.external_auth_id is None:
                try:
                    provisioned = self.provisioning.provision_tenant_admin(
                        email=normalized_email,
                        name=user.name or normalized_email.split("@")[0],
                    )
                    user.external_auth_id = provisioned.external_auth_id
                except ProvisioningConflictError as exc:
                    if exc.status_code == 409:
                        try:
                            self.provisioning.trigger_password_reset_email(
                                email=normalized_email
                            )
                        except Exception as reset_exc:
                            logger.warning("Failed triggering Auth0 password reset on 409: %s", reset_exc)
                    else:
                        logger.warning("Auth0 provisioning error for existing DB user: %s", exc)
                except Exception as exc:
                    logger.warning("Unexpected error provisioning existing DB user: %s", exc)
            else:
                try:
                    self.provisioning.trigger_password_reset_email(
                        email=normalized_email
                    )
                except Exception as exc:
                    logger.warning("Failed triggering password reset for existing user: %s", exc)

            try:
                ticket_url = self.provisioning.create_password_change_ticket(
                    email=normalized_email
                )
            except Exception as exc:
                logger.warning("Could not create password ticket for existing user: %s", exc)

        existing = self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user.id,
            )
        )
        if existing is not None:
            raise MembershipAlreadyExistsError(f"User '{email}' already has a membership in this tenant")

        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=role.strip(),
            status="active",
        )
        self.db.add(membership)
        from sqlalchemy.exc import IntegrityError

        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            existing = self.db.scalar(
                select(TenantMembership).where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == user.id,
                )
            )
            if existing is None:
                raise exc
            raise MembershipAlreadyExistsError(
                f"User '{email}' already has a membership in this tenant"
            ) from exc
        self.db.refresh(membership)
        if ticket_url:
            setattr(membership, "password_reset_url", ticket_url)
        return membership

    def get_membership(self, tenant_id: str, membership_id: str) -> TenantMembership | None:
        return self.db.scalar(
            select(TenantMembership)
            .options(joinedload(TenantMembership.user))
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == membership_id,
            )
        )

    def delete_membership(self, tenant_id: str, membership_id: str) -> dict:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")

        membership = self.db.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == membership_id,
            )
        )
        if membership is None:
            raise ValueError(f"Membership '{membership_id}' not found in tenant '{tenant_id}'")

        admin_roles = ADMIN_ROLES
        if membership.role in admin_roles and membership.status == "active":
            active_admins = list(
                self.db.scalars(
                    select(TenantMembership).where(
                        TenantMembership.tenant_id == tenant_id,
                        TenantMembership.role.in_(admin_roles),
                        TenantMembership.status == "active",
                    )
                ).all()
            )
            if len(active_admins) <= 1:
                raise ValueError("No se puede eliminar la única membresía de administrador activa del tenant.")

        self.db.delete(membership)
        self.db.commit()
        return {
            "deleted": True,
            "membership_id": membership_id,
            "tenant_id": tenant_id,
        }

    def send_membership_password_reset(self, tenant_id: str, membership_id: str) -> PasswordResetOutcome:
        """Make sure the member has an external account, then email (and offer a ticket for) a password change.

        Raises ``MembershipNotFoundError`` (no membership/user/email) or ``PasswordResetFailedError`` (the provider
        could not send the email and no fallback ticket could be created). Provider internals are never exposed.
        """
        membership = self.get_membership(tenant_id, membership_id)
        if not membership or not membership.user or not membership.user.email:
            raise MembershipNotFoundError("Membership or user not found")

        user = membership.user
        email = user.email
        if user.external_auth_id is None:
            try:
                provisioned = self.provisioning.provision_tenant_admin(
                    email=email, name=user.name or email.split("@")[0]
                )
                user.external_auth_id = provisioned.external_auth_id
                self.db.commit()
            except (IdentityProviderError, ProvisioningConflictError) as exc:
                if exc.status_code != 409:
                    logger.warning("Identity provider provisioning error on password reset: %s", exc)

        error_detail: str | None = None
        try:
            self.provisioning.trigger_password_reset_email(email=email)
        except (IdentityProviderError, ProvisioningConflictError) as exc:
            error_detail = str(exc)
            logger.warning("trigger_password_reset_email failed: %s", exc)

        ticket_url: str | None = None
        try:
            ticket_url = self.provisioning.create_password_change_ticket(email=email)
        except Exception as exc:
            logger.warning("create_password_change_ticket failed: %s", exc)

        if error_detail and not ticket_url:
            raise PasswordResetFailedError(f"No se pudo enviar el correo de contraseña: {error_detail}")
        return PasswordResetOutcome(email=email, ticket_url=ticket_url)

    def list_memberships(self, tenant_id: str) -> list[TenantMembership]:
        tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")

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
    ) -> LegacyAgentView:
        if self.db.get(Tenant, tenant_id) is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")
        agent = self.legacy_agents.create_agents(tenant_id, ({
            "name": name,
            "external_provider": external_provider,
            "external_agent_id": external_agent_id,
            "channel_type": channel_type,
            "status": status,
        },))[0]
        self.db.commit()
        return agent

    def list_agents(self, tenant_id: str) -> tuple[LegacyAgentView, ...]:
        if self.db.get(Tenant, tenant_id) is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' not found")
        return self.legacy_agents.list_agents(tenant_id)

    def _build_tenant_response(
        self,
        tenant: Tenant,
        admin_user: User,
        membership: TenantMembership,
        agents: tuple[LegacyAgentView, ...],
        *,
        auth0_provisioning: ProvisionedUser | None = None,
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
        usage = self.billing.tenant_usage_snapshot(tenant.id)

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
            "usage": dict(usage),
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
        from app.core.config import settings

        if tenant.slug == settings.BOOTSTRAP_TENANT_SLUG:
            raise TenantDeletionBlockedError(
                f"Tenant '{tenant.slug}' is the bootstrap tenant and cannot be deleted"
            )

    def _delete_count(self, statement) -> int:
        result = self.db.execute(statement)
        return max(result.rowcount or 0, 0)
