import os
import subprocess
import sys
import unittest
from pathlib import Path


class IdentityBoundaryTests(unittest.TestCase):
    def test_public_import_does_not_load_framework_or_internal_layers(self):
        code = (
            "import sys; import app.modules.identity.public; "
            "bad = {m for m in sys.modules if m.startswith('app.modules.identity.') "
            "and m.split('.')[3] in {'application', 'infrastructure', 'api'}}; "
            "bad |= {m for m in sys.modules if m.split('.')[0] in ('fastapi', 'sqlalchemy', 'httpx', 'jwt')}; assert not bad, bad"
        )
        subprocess.run([sys.executable, "-c", code], check=True, cwd=Path(__file__).parent)

    def test_identity_tables_are_owned_by_identity_models(self):
        from app.modules.identity.infrastructure.models import (
            AccessAuditLog, Tenant, TenantFeatureGrant, TenantMembership, User
        )
        expected = {
            "tenants": Tenant,
            "users": User,
            "tenant_memberships": TenantMembership,
            "access_audit_logs": AccessAuditLog,
            "tenant_feature_grants": TenantFeatureGrant,
        }
        self.assertEqual({model.__tablename__ for model in expected.values()}, set(expected))
        self.assertTrue(all(model.__module__ == "app.modules.identity.infrastructure.models" for model in expected.values()))

    def test_legacy_identity_paths_are_removed(self):
        root = Path(__file__).parent / "app"
        for path in (
            "models/identity.py", "models/tenant_features.py",
            "services/identity_service.py", "services/bootstrap_service.py",
            "services/tenant_feature_service.py", "services/auth0_service.py",
            "services/auth0_provisioning_service.py", "api/auth/deps.py",
        ):
            with self.subTest(path=path):
                self.assertFalse((root / path).exists())


if __name__ == "__main__":
    unittest.main()
