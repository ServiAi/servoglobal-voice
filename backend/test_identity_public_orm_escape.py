"""Calls the public Identity APIs for real and checks that no ORM instance ever comes back."""

from __future__ import annotations

import os
import unittest
from collections.abc import Mapping

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

import app.models  # noqa: F401  (register every ORM table before create_all)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.modules.identity.infrastructure.auth0.provisioning import Auth0ProvisionedUser
from app.modules.identity.infrastructure.models import (
    AccessAuditLog,
    Tenant,
    TenantFeatureGrant,
    TenantMembership,
    User,
)
from app.modules.identity.public import (
    AGENT_BUILDER,
    AccessAudit,
    FeatureFlags,
    IdentityAdminFacade,
    IdentityFacade,
    MembershipDirectory,
    PasswordResetResult,
    TenantDirectory,
    TenantLifecycle,
)

ORM_TYPES = (Tenant, User, TenantMembership, AccessAuditLog, TenantFeatureGrant)


class FakeAuth0:
    def provision_tenant_admin(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        return Auth0ProvisionedUser(
            user_id=f"auth0|{email}",
            email=email,
            name=name,
            connection="db",
            verification_email_sent=True,
            password_reset_triggered=True,
        )

    def trigger_password_reset_email(self, *, email: str) -> None:
        return None

    def create_password_change_ticket(self, *, email: str, **kwargs) -> str | None:
        return "https://example.test/ticket"

    def delete_user(self, user_id: str) -> None:
        return None


def contains_orm(value: object, _depth: int = 0) -> bool:
    if isinstance(value, ORM_TYPES):
        return True
    if _depth > 6:
        return False
    if isinstance(value, Mapping):
        return any(contains_orm(v, _depth + 1) for v in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(contains_orm(v, _depth + 1) for v in value)
    if hasattr(value, "__dataclass_fields__"):
        return any(contains_orm(getattr(value, name), _depth + 1) for name in value.__dataclass_fields__)
    return False


class IdentityPublicOrmEscapeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        self.engine = engine
        self.db = sessionmaker(bind=engine, expire_on_commit=False)()
        tenant = Tenant(name="Acme", slug="acme", timezone="UTC", status="active")
        user = User(email="admin@acme.test", name="Admin", is_internal=False, status="active", external_auth_id="auth0|1")
        self.db.add_all([tenant, user])
        self.db.flush()
        self.membership = TenantMembership(tenant_id=tenant.id, user_id=user.id, role="tenant_admin", status="active")
        self.db.add(self.membership)
        self.db.commit()
        self.tenant_id, self.user_id = tenant.id, user.id

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def assertNoOrm(self, label: str, value: object) -> None:
        self.assertFalse(contains_orm(value), f"{label} returned an ORM instance: {value!r}")

    def test_directories_and_lifecycle_return_dtos_only(self):
        tenants = TenantDirectory(self.db)
        members = MembershipDirectory(self.db)
        calls = {
            "TenantDirectory.get": tenants.get(self.tenant_id),
            "TenantDirectory.get_by_slug": tenants.get_by_slug("acme"),
            "TenantDirectory.require": tenants.require(self.tenant_id),
            "TenantDirectory.bootstrap": tenants.bootstrap(),
            "MembershipDirectory.get": members.get(self.tenant_id, user_id=self.user_id),
            "MembershipDirectory.list": members.list(self.tenant_id),
            "TenantLifecycle.set_usage_suspension": TenantLifecycle(self.db).set_usage_suspension(
                self.tenant_id, True
            ),
            "IdentityFacade.membership_directory": IdentityFacade(self.db).membership_directory().list(self.tenant_id),
            "IdentityFacade.tenant_directory": IdentityFacade(self.db).tenant_directory().get(self.tenant_id),
        }
        for label, value in calls.items():
            self.assertNoOrm(label, value)
        self.assertIsNone(AccessAudit(self.db).record(user_id=self.user_id, tenant_id=self.tenant_id, action="x", resource="y"))

    def test_feature_flags_return_dtos_only(self):
        flags = FeatureFlags(self.db)
        grant = flags.set_feature(self.tenant_id, AGENT_BUILDER, True, {}, self.user_id)
        for label, value in {
            "set_feature": grant,
            "list_features": flags.list_features(self.tenant_id),
            "require_enabled": flags.require_enabled(self.tenant_id, AGENT_BUILDER),
            "is_enabled": flags.is_enabled(self.tenant_id, AGENT_BUILDER),
        }.items():
            self.assertNoOrm(f"FeatureFlags.{label}", value)

    def test_admin_facade_returns_dtos_mappings_or_primitives_only(self):
        admin = IdentityAdminFacade(self.db, FakeAuth0())
        membership_id = self.membership.id
        added = admin.add_membership(self.tenant_id, email="new@acme.test", role="tenant_analyst")
        for label, value in {
            "list_tenants": admin.list_tenants(),
            "get_tenant": admin.get_tenant(self.tenant_id),
            "update_tenant": admin.update_tenant(self.tenant_id, name="Acme 2", timezone="UTC", status="active"),
            "list_memberships": admin.list_memberships(self.tenant_id),
            "get_membership": admin.get_membership(self.tenant_id, membership_id),
            "add_membership": added,
            "send_membership_password_reset": admin.send_membership_password_reset(self.tenant_id, added.id),
            "delete_membership": admin.delete_membership(self.tenant_id, added.id),
        }.items():
            self.assertNoOrm(f"IdentityAdminFacade.{label}", value)

    def test_password_reset_result_for_a_member_without_an_external_account(self):
        admin = IdentityAdminFacade(self.db, FakeAuth0())
        added = admin.add_membership(self.tenant_id, email="nolink@acme.test", role="tenant_analyst")
        user = self.db.get(User, added.user_id)
        user.external_auth_id = None
        self.db.commit()
        result = admin.send_membership_password_reset(self.tenant_id, added.id)
        self.assertIsInstance(result, PasswordResetResult)
        self.assertTrue(result.success)
        self.assertIn("nolink@acme.test", result.detail)
        self.assertEqual(result.ticket_url, "https://example.test/ticket")
        self.db.refresh(user)
        self.assertEqual(user.external_auth_id, "auth0|nolink@acme.test")


if __name__ == "__main__":
    unittest.main()
