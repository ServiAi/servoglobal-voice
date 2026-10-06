import ast
import subprocess
import sys
import unittest
from pathlib import Path

APP = Path(__file__).parent / "app"
BILLING = APP / "modules" / "billing"


def imports(path: Path) -> set[str]:
    result = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


class BillingBoundaryTests(unittest.TestCase):
    def test_billing_mappers_do_not_navigate_to_tenant(self):
        from sqlalchemy import inspect
        from sqlalchemy.orm import configure_mappers

        from app.models import Tenant  # noqa: F401 - register the Tenant mapper
        from app.modules.billing.infrastructure.models import TenantBillingPlan, TenantUsageAlert

        configure_mappers()
        self.assertEqual(set(inspect(TenantBillingPlan).relationships.keys()), {"alerts"})
        self.assertEqual(set(inspect(TenantUsageAlert).relationships.keys()), {"billing_plan"})
        for model in (TenantBillingPlan, TenantUsageAlert):
            tenant_fk = model.__table__.c.tenant_id.foreign_keys
            self.assertEqual({fk.target_fullname for fk in tenant_fk}, {"tenants.id"})

    def test_domain_is_pure(self):
        forbidden = ("sqlalchemy", "fastapi", "starlette", "pydantic", "httpx", "app.models", "app.services", "app.api", "app.modules.identity", "app.modules.analytics")
        offenders = [
            f"{path.relative_to(BILLING)} imports {module}"
            for path in (BILLING / "domain").rglob("*.py")
            for module in imports(path)
            if module.startswith(forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_application_has_no_framework_or_foreign_orm_dependency(self):
        forbidden = ("fastapi", "starlette", "pydantic", "app.models.analytics", "app.modules.identity.infrastructure", "app.services", "app.modules.billing.api")
        offenders = [
            f"{path.relative_to(BILLING)} imports {module}"
            for path in (BILLING / "application").rglob("*.py")
            for module in imports(path)
            if module.startswith(forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_only_wiring_imports_legacy_analytics_orm(self):
        offenders = [
            f"{path.relative_to(BILLING)} imports {module}"
            for path in BILLING.rglob("*.py")
            for module in imports(path)
            if module == "app.models.analytics" and path != BILLING / "wiring.py"
        ]
        self.assertEqual(offenders, [])

    def test_public_import_is_light(self):
        code = (
            "import json,sys; import app.modules.billing.public; "
            "print(json.dumps(sorted(x for x in sys.modules if x == 'sqlalchemy' "
            "or x.startswith(('fastapi','pydantic','app.models.analytics',"
            "'app.modules.billing.application','app.modules.billing.infrastructure',"
            "'app.modules.billing.api','app.modules.identity.infrastructure')))))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).parent,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip(), "[]")

    def test_no_legacy_billing_production_imports(self):
        forbidden = {"app.models.billing", "app.services.tenant_usage_service"}
        offenders = [
            f"{path.relative_to(APP)} imports {module}"
            for path in APP.rglob("*.py")
            for module in imports(path)
            if module in forbidden
        ]
        self.assertEqual(offenders, [])

    def test_only_wiring_reads_analytics_legacy_and_other_modules_use_public(self):
        private_imports = []
        identity_billing_imports = []
        for path in APP.rglob("*.py"):
            for module in imports(path):
                if path.is_relative_to(BILLING) and module == "app.models.analytics" and path != BILLING / "wiring.py":
                    private_imports.append(f"{path.relative_to(APP)} -> {module}")
                if module.startswith("app.modules.billing"):
                    if path.is_relative_to(BILLING):
                        continue
                    if path == APP / "main.py" and module.startswith("app.modules.billing.api"):
                        continue
                    if path == APP / "models" / "__init__.py" and module == "app.modules.billing.infrastructure.models":
                        continue
                    if module != "app.modules.billing.public":
                        private_imports.append(f"{path.relative_to(APP)} -> {module}")
                if path == APP / "modules" / "identity" / "wiring.py" and module.startswith("app.modules.billing") and module != "app.modules.billing.public":
                    identity_billing_imports.append(module)
        self.assertEqual(private_imports, [])
        self.assertEqual(identity_billing_imports, [])

    def test_billing_routes_exist_once_and_contract_metrics_match(self):
        from app.api.endpoints.admin import tenants as admin_tenants
        from app.api.endpoints import dashboard
        from app.main import app
        from app.modules.billing.api import admin_router, dashboard_router

        router_paths = (
            (dashboard.router, "/api/v1/dashboard/usage", "GET"),
            (dashboard.router, "/api/v1/dashboard/savings-comparison", "GET"),
            (dashboard_router.router, "/api/v1/dashboard/usage", "GET"),
            (dashboard_router.router, "/api/v1/dashboard/savings-comparison", "GET"),
            (admin_tenants.router, "/api/v1/admin/tenants/usage-summary", "GET"),
            (admin_tenants.router, "/api/v1/admin/usage-alerts", "GET"),
            (admin_tenants.router, "/api/v1/admin/tenants/{tenant_id}/usage", "GET"),
            (admin_tenants.router, "/api/v1/admin/tenants/{tenant_id}/plan", "PATCH"),
            (admin_router.router, "/api/v1/admin/tenants/usage-summary", "GET"),
            (admin_router.router, "/api/v1/admin/usage-alerts", "GET"),
            (admin_router.router, "/api/v1/admin/tenants/{tenant_id}/usage", "GET"),
            (admin_router.router, "/api/v1/admin/tenants/{tenant_id}/plan", "PATCH"),
        )
        for router, path, method in router_paths:
            routes = [r for r in router.routes if r.path == path and method in r.methods]
            if router in (dashboard.router, admin_tenants.router):
                self.assertEqual(routes, [], f"legacy router still owns {method} {path}")
            else:
                self.assertEqual(len(routes), 1, f"Billing route count for {method} {path}")

        schema = app.openapi()
        methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
        operations = sum(1 for path in schema["paths"].values() for method in path if method.lower() in methods)
        self.assertEqual((len(schema["paths"]), operations, len(schema["components"]["schemas"])), (257, 336, 293))
        expected = {
            "/api/v1/dashboard/usage": {"get"},
            "/api/v1/dashboard/savings-comparison": {"get"},
            "/api/v1/admin/tenants/usage-summary": {"get"},
            "/api/v1/admin/usage-alerts": {"get"},
            "/api/v1/admin/tenants/{tenant_id}/usage": {"get"},
            "/api/v1/admin/tenants/{tenant_id}/plan": {"patch"},
        }
        for path, methods in expected.items():
            self.assertEqual(set(schema["paths"][path]), methods)


if __name__ == "__main__":
    unittest.main()
