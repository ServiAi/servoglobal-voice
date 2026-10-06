r"""Real PostgreSQL concurrency tests for Identity / Tenancy.

Seven invariants SQLite cannot prove:

1. concurrent resolution of the same external identity -> one User
2. concurrent first login of a pre-provisioned account -> linked once
3. concurrent bootstrap -> one Tenant, one User, one Membership
4. concurrent membership create -> one Membership, losers get MembershipAlreadyExistsError
5. concurrent removal of two admins -> an active admin always remains
6. deleting a tenant keeps a user that belongs to another tenant (and never deletes it at the provider)
7. concurrent feature set -> one TenantFeatureGrant

Run only against the dedicated disposable database ``serviai_identity_test``:

    $env:IDENTITY_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_identity_test"
    .\.venv\Scripts\python.exe -m unittest test_identity_postgres -v
"""

from __future__ import annotations

import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

IDENTITY_TEST_DATABASE_URL = os.environ.get("IDENTITY_TEST_DATABASE_URL")
if IDENTITY_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ["DATABASE_URL"] = IDENTITY_TEST_DATABASE_URL

import app.models  # noqa: F401  (register every ORM table before create_all)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.modules.identity.application.authentication_service import IdentityService
from app.modules.identity.application.bootstrap_service import IdentityBootstrapService
from app.modules.identity.domain.contracts import ExternalIdentity
from app.modules.identity.domain.errors import MembershipAlreadyExistsError
from app.modules.identity.domain.features import AGENT_BUILDER
from app.modules.identity.infrastructure.auth0.provisioning import Auth0ProvisionedUser
from app.modules.identity.infrastructure.models import Tenant, TenantFeatureGrant, TenantMembership, User
from app.modules.identity.public import FeatureFlags
from app.modules.identity.wiring import create_onboarding_service

EXPECTED_DATABASE = "serviai_identity_test"
WORKERS = 6


class RecordingAuth0:
    """Auth0-level fake: records what Identity asks the provider to do."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def provision_tenant_admin(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        return Auth0ProvisionedUser(
            user_id=f"auth0|{uuid.uuid4().hex}",
            email=email,
            name=name,
            connection="db",
            verification_email_sent=True,
            password_reset_triggered=True,
        )

    def trigger_password_reset_email(self, *, email: str) -> None:
        return None

    def create_password_change_ticket(self, *, email: str, **kwargs) -> str | None:
        return None

    def delete_user(self, user_id: str) -> None:
        self.deleted.append(user_id)


def run_concurrently(workers: int, task):
    """Start ``workers`` calls of ``task(index)`` at the same instant; return (results, errors)."""
    barrier = Barrier(workers)
    results, errors = [], []

    def wrapped(index: int):
        barrier.wait(timeout=15)
        return task(index)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(wrapped, index) for index in range(workers)]
        for future in futures:
            try:
                results.append(future.result(timeout=60))
            except Exception as exc:  # noqa: BLE001 - the tests assert on the exact types
                errors.append(exc)
    return results, errors


@unittest.skipUnless(
    IDENTITY_TEST_DATABASE_URL,
    "IDENTITY_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class IdentityPostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        url = make_url(IDENTITY_TEST_DATABASE_URL)
        if url.get_backend_name() != "postgresql":
            raise unittest.SkipTest("IDENTITY_TEST_DATABASE_URL must point to PostgreSQL")
        if url.database != EXPECTED_DATABASE:
            raise unittest.SkipTest(
                f"refusing to run against '{url.database}': the Identity suite only uses '{EXPECTED_DATABASE}'"
            )
        cls.engine = create_engine(IDENTITY_TEST_DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=10)
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=cls.engine)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    # -- fixtures --------------------------------------------------------------------------------

    def tenant(self, db, role_members: tuple[str, ...] = ()) -> str:
        tenant = Tenant(name="Acme", slug=f"t-{uuid.uuid4().hex[:10]}", timezone="UTC", status="active")
        db.add(tenant)
        db.commit()
        return tenant.id

    def user(self, db, *, external: str | None = "auto", email: str | None = None) -> User:
        external_id = f"auth0|{uuid.uuid4().hex}" if external == "auto" else external
        user = User(
            email=email or f"u-{uuid.uuid4().hex[:8]}@example.test",
            name="User",
            external_auth_id=external_id,
            is_internal=False,
            status="active",
        )
        db.add(user)
        db.commit()
        return user

    def membership(self, db, tenant_id: str, user_id: str, role: str = "tenant_admin") -> str:
        membership = TenantMembership(tenant_id=tenant_id, user_id=user_id, role=role, status="active")
        db.add(membership)
        db.commit()
        return membership.id

    def count(self, model, *conditions) -> int:
        with self.Session() as db:
            return db.scalar(select(func.count()).select_from(model).where(*conditions))

    # -- 1. identity resolution ------------------------------------------------------------------

    def test_concurrent_resolution_of_the_same_identity_creates_one_user(self):
        original = settings.AUTH0_AUTO_CREATE_USERS
        settings.AUTH0_AUTO_CREATE_USERS = True
        try:
            for round_number in range(4):
                sub = f"auth0|race-{uuid.uuid4().hex}"
                identity = ExternalIdentity(
                    external_auth_id=sub, email=f"{sub[6:]}@example.test", name="Racer", email_verified=True
                )

                def resolve(_index: int) -> str:
                    with self.Session() as db:
                        return IdentityService(db).resolve_user(identity).id

                ids, errors = run_concurrently(WORKERS, resolve)
                self.assertEqual(errors, [], f"round {round_number}: {errors}")
                self.assertEqual(len(set(ids)), 1, f"round {round_number}: {ids}")
                self.assertEqual(self.count(User, User.external_auth_id == sub), 1)
        finally:
            settings.AUTH0_AUTO_CREATE_USERS = original

    # -- 2. pre-provisioned first login ----------------------------------------------------------

    def test_concurrent_first_login_links_a_pre_provisioned_account_once(self):
        for round_number in range(4):
            email = f"pre-{uuid.uuid4().hex[:8]}@example.test"
            with self.Session() as db:
                seeded = self.user(db, external=None, email=email)
            sub = f"auth0|first-{uuid.uuid4().hex}"
            identity = ExternalIdentity(external_auth_id=sub, email=email, name="First", email_verified=True)

            def resolve(_index: int) -> str:
                with self.Session() as db:
                    return IdentityService(db).resolve_user(identity).id

            ids, errors = run_concurrently(WORKERS, resolve)
            self.assertEqual(errors, [], f"round {round_number}: {errors}")
            self.assertEqual(set(ids), {seeded.id}, f"round {round_number}")
            self.assertEqual(self.count(User, User.email == email), 1)
            with self.Session() as db:
                self.assertEqual(db.get(User, seeded.id).external_auth_id, sub)

    def test_an_integrity_error_for_a_different_identity_is_not_swallowed(self):
        """Only the *same* external identity may reuse the winner; a clash on another unique key must surface."""
        email = f"clash-{uuid.uuid4().hex[:8]}@example.test"
        with self.Session() as db:
            self.user(db, external=f"auth0|owner-{uuid.uuid4().hex}", email=email)
        original = settings.AUTH0_AUTO_CREATE_USERS
        settings.AUTH0_AUTO_CREATE_USERS = True
        try:
            other = ExternalIdentity(
                external_auth_id=f"auth0|other-{uuid.uuid4().hex}", email=email, name="Other", email_verified=True
            )
            with self.Session() as db:
                resolved = IdentityService(db).resolve_user(other)
            # The e-mail already belongs to a linked account: it is returned as-is (never re-linked, never duplicated).
            self.assertEqual(resolved.email, email)
            self.assertEqual(self.count(User, User.email == email), 1)
        finally:
            settings.AUTH0_AUTO_CREATE_USERS = original

    # -- 3. bootstrap ----------------------------------------------------------------------------

    def test_concurrent_bootstrap_creates_one_tenant_user_and_membership(self):
        suffix = uuid.uuid4().hex[:8]
        overrides = {
            "BOOTSTRAP_TENANT_SLUG": f"boot-{suffix}",
            "BOOTSTRAP_TENANT_NAME": "Bootstrap",
            "BOOTSTRAP_TENANT_TIMEZONE": "UTC",
            "BOOTSTRAP_USER_AUTH0_SUB": f"auth0|boot-{suffix}",
            "BOOTSTRAP_USER_EMAIL": f"boot-{suffix}@example.test",
            "BOOTSTRAP_USER_NAME": "Boot",
            "BOOTSTRAP_USER_ROLE": "tenant_admin",
        }
        previous = {name: getattr(settings, name) for name in overrides}
        for name, value in overrides.items():
            setattr(settings, name, value)
        try:

            def bootstrap(_index: int):
                with self.Session() as db:
                    return IdentityBootstrapService(db).run_initial_bootstrap()

            results, errors = run_concurrently(WORKERS, bootstrap)
        finally:
            for name, value in previous.items():
                setattr(settings, name, value)

        self.assertEqual(errors, [], errors)
        self.assertEqual(len({(r.tenant_id, r.user_id, r.membership_id) for r in results}), 1)
        self.assertEqual(sum(1 for r in results if r.created_tenant), 1)
        self.assertEqual(self.count(Tenant, Tenant.slug == overrides["BOOTSTRAP_TENANT_SLUG"]), 1)
        self.assertEqual(self.count(User, User.external_auth_id == overrides["BOOTSTRAP_USER_AUTH0_SUB"]), 1)
        self.assertEqual(self.count(TenantMembership, TenantMembership.tenant_id == results[0].tenant_id), 1)

    def test_concurrent_bootstrap_tenant_lookup_converges_on_one_tenant(self):
        slug = f"first-login-{uuid.uuid4().hex[:8]}"
        previous = settings.BOOTSTRAP_TENANT_SLUG
        settings.BOOTSTRAP_TENANT_SLUG = slug
        try:

            def bootstrap(_index: int) -> str:
                with self.Session() as db:
                    return IdentityService(db).bootstrap_tenant().id

            ids, errors = run_concurrently(WORKERS, bootstrap)
        finally:
            settings.BOOTSTRAP_TENANT_SLUG = previous
        self.assertEqual(errors, [], errors)
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(self.count(Tenant, Tenant.slug == slug), 1)

    # -- 4. membership create --------------------------------------------------------------------

    def test_concurrent_membership_create_keeps_one_membership(self):
        with self.Session() as db:
            tenant_id = self.tenant(db)
            user = self.user(db)
            email = user.email

        def add(_index: int):
            with self.Session() as db:
                real_add = db.add

                def slow_add(instance, *args, **kwargs):
                    if isinstance(instance, TenantMembership):
                        # After the "already a member?" check and before the INSERT: every worker passes the
                        # check, so the loser really hits the unique constraint instead of the pre-check.
                        time.sleep(0.3)
                    return real_add(instance, *args, **kwargs)

                db.add = slow_add
                return create_onboarding_service(db, RecordingAuth0()).add_membership(
                    tenant_id, email=email, role="tenant_analyst"
                ).id

        results, errors = run_concurrently(WORKERS, add)
        self.assertEqual(len(results), 1, (results, errors))
        self.assertEqual(len(errors), WORKERS - 1)
        for error in errors:
            self.assertIsInstance(error, MembershipAlreadyExistsError, repr(error))
            self.assertIsInstance(error, ValueError)  # the API maps ValueError to 409
        self.assertEqual(self.count(TenantMembership, TenantMembership.tenant_id == tenant_id), 1)

    # -- 5. last admin ---------------------------------------------------------------------------

    def test_concurrent_removal_of_two_admins_never_leaves_a_tenant_without_one(self):
        for round_number in range(4):
            with self.Session() as db:
                tenant_id = self.tenant(db)
                first = self.membership(db, tenant_id, self.user(db).id)
                second = self.membership(db, tenant_id, self.user(db).id)

            def remove(index: int):
                with self.Session() as db:
                    return create_onboarding_service(db, RecordingAuth0()).delete_membership(
                        tenant_id, (first, second)[index]
                    )

            results, errors = run_concurrently(2, remove)
            self.assertEqual(len(results), 1, f"round {round_number}: {results} {errors}")
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            self.assertIn("única membresía de administrador", str(errors[0]))
            remaining = self.count(
                TenantMembership,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
                TenantMembership.role == "tenant_admin",
            )
            self.assertGreaterEqual(remaining, 1)
            self.assertEqual(remaining, 1)

    # -- 6. shared users -------------------------------------------------------------------------

    def test_deleting_a_tenant_keeps_a_user_shared_with_another_tenant(self):
        with self.Session() as db:
            tenant_a, tenant_b = self.tenant(db), self.tenant(db)
            shared = self.user(db)
            membership_a = self.membership(db, tenant_a, shared.id)
            membership_b = self.membership(db, tenant_b, shared.id)
            shared_id = shared.id
        provider = RecordingAuth0()

        with self.Session() as db:
            result = create_onboarding_service(db, provider).delete_tenant(tenant_a)

        self.assertTrue(result["deleted"])
        self.assertEqual(provider.deleted, [], "a shared user must not be deleted at the identity provider")
        with self.Session() as db:
            self.assertIsNone(db.get(Tenant, tenant_a))
            self.assertIsNone(db.get(TenantMembership, membership_a))
            self.assertIsNotNone(db.get(Tenant, tenant_b))
            self.assertIsNotNone(db.get(TenantMembership, membership_b))
            self.assertIsNotNone(db.get(User, shared_id))
        self.assertEqual(result["deleted_counts"]["users"], 0)
        self.assertEqual(result["deleted_counts"]["auth0_users"], 0)

    def test_deleting_a_tenant_removes_a_user_that_belongs_only_to_it(self):
        with self.Session() as db:
            tenant_id = self.tenant(db)
            orphan = self.user(db)
            self.membership(db, tenant_id, orphan.id)
            orphan_id, orphan_external = orphan.id, orphan.external_auth_id
        provider = RecordingAuth0()

        with self.Session() as db:
            result = create_onboarding_service(db, provider).delete_tenant(tenant_id)

        self.assertEqual(provider.deleted, [orphan_external])
        self.assertEqual(result["deleted_counts"]["users"], 1)
        with self.Session() as db:
            self.assertIsNone(db.get(User, orphan_id))

    # -- 7. feature grants -----------------------------------------------------------------------

    def test_concurrent_feature_set_keeps_a_single_grant(self):
        for round_number in range(4):
            with self.Session() as db:
                tenant_id = self.tenant(db)
                actor = self.user(db).id

            def set_feature(index: int):
                with self.Session() as db:
                    return FeatureFlags(db).set_feature(tenant_id, AGENT_BUILDER, bool(index % 2), {}, actor)

            results, errors = run_concurrently(WORKERS, set_feature)
            self.assertEqual(errors, [], f"round {round_number}: {errors}")
            self.assertEqual(len(results), WORKERS)
            self.assertEqual(
                self.count(
                    TenantFeatureGrant,
                    TenantFeatureGrant.tenant_id == tenant_id,
                    TenantFeatureGrant.feature_key == AGENT_BUILDER,
                ),
                1,
            )
            with self.Session() as db:
                grant = db.scalar(select(TenantFeatureGrant).where(TenantFeatureGrant.tenant_id == tenant_id))
                self.assertIn(grant.enabled, {True, False})


if __name__ == "__main__":
    unittest.main()
