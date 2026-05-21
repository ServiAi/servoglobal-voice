from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.analytics import Agent
from app.models.identity import Tenant, TenantMembership, User


class OnboardingService:
    def __init__(self, db: Session) -> None:
        self.db = db

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

        existing_tenant = self.db.scalar(
            select(Tenant).where(Tenant.slug == slug)
        )
        if existing_tenant is not None:
            raise ValueError(f"Tenant slug '{slug}' already exists")

        existing_user = self.db.scalar(
            select(User).where(User.email == admin_email)
        )
        if existing_user is not None and existing_user.external_auth_id is not None:
            raise ValueError(f"A user with external_auth_id already exists for email '{admin_email}'")

        tenant = Tenant(
            name=name.strip(),
            slug=slug,
            timezone=timezone,
            status=status,
        )
        self.db.add(tenant)
        self.db.flush()

        admin_user = User(
            external_auth_id=None,
            email=admin_email.strip().lower(),
            name=admin_name.strip(),
            is_internal=False,
            status="active",
        )
        self.db.add(admin_user)
        self.db.flush()

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

        return self._build_tenant_response(tenant, admin_user, membership, agent_list)

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
                "has_auth0_link": admin_user.external_auth_id is not None,
            },
            "memberships": member_dicts,
            "agents": agent_dicts,
            "is_ready_for_calls": len(agent_dicts) > 0,
        }
