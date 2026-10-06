"""Architecture tests of the Identity / Tenancy module: layers, public surface and ORM ownership."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

BACKEND = Path(__file__).parent
APP = BACKEND / "app"
IDENTITY = APP / "modules" / "identity"
ORM_NAMES = {"Tenant", "User", "TenantMembership", "AccessAuditLog", "TenantFeatureGrant"}
ORM_MODULES = {"app.modules.identity.infrastructure.models", "app.models"}
# Legacy code that still reads Tenant (through the app.models registry) until its owner module exists.
TENANT_DIRECT_READERS = {
    "services/crm_dashboard_metrics_service.py": "CRM/Analytics dashboard read-model (future Analytics owner)",
    "services/dashboard_analytics_service.py": "Analytics dashboard (future Analytics owner)",
    "services/public_voice_call_service.py": "Voice Experiences public calls (future Voice Experiences owner)",
    "services/ultravox_ingestion_service.py": "Voice Legacy ingestion (future Voice Legacy owner)",
    "services/voice_callback_service.py": "Voice Legacy callbacks (future Voice Legacy owner)",
    "api/endpoints/voice.py": "Voice Legacy endpoint (future Voice Legacy owner)",
}
MIGRATED_MODULES = (
    "tools",
    "agents",
    "voice",
    "voice_providers",
    "telephony",
    "scheduling",
    "crm",
    "notifications",
    "integrations",
)
FORBIDDEN_EXPORTS = {
    "IdentityService",
    "IdentityBootstrapService",
    "OnboardingService",
    "create_onboarding_service",
    "create_provisioning_adapter",
    "get_current_auth_context",
    "get_current_identity",
    "get_current_internal_user",
    "get_identity_provisioning_port",
    "require_roles",
    "Tenant",
    "User",
    "TenantMembership",
    "AccessAuditLog",
    "TenantFeatureGrant",
}


def _targets(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _orm_reads(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.ImportFrom) and node.module in ORM_MODULES:
            names |= {alias.name for alias in node.names} & ORM_NAMES
    return names


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


class IdentityLayerPurityTests(unittest.TestCase):
    def test_application_and_domain_never_import_the_http_framework(self):
        forbidden = ("fastapi", "starlette", "app.modules.identity.api")
        offenders = [
            f"{_rel(path)}: {target}"
            for layer in ("application", "domain")
            for path in (IDENTITY / layer).rglob("*.py")
            for target in _targets(path)
            if target.startswith(forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_domain_is_pure(self):
        forbidden = (
            "fastapi",
            "starlette",
            "sqlalchemy",
            "httpx",
            "jwt",
            "pydantic",
            "app.services",
            "app.models",
            "app.db",
            "app.core",
        )
        offenders = []
        for path in (IDENTITY / "domain").rglob("*.py"):
            for target in _targets(path):
                other_layer = target.startswith("app.modules.identity.") and not target.startswith(
                    "app.modules.identity.domain"
                )
                if target.startswith(forbidden) or other_layer:
                    offenders.append(f"{_rel(path)}: {target}")
        self.assertEqual(offenders, [])

    def test_infrastructure_does_not_depend_on_the_http_framework_or_api(self):
        forbidden = ("fastapi", "starlette", "app.modules.identity.api", "app.modules.identity.application")
        offenders = [
            f"{_rel(path)}: {target}"
            for path in (IDENTITY / "infrastructure").rglob("*.py")
            for target in _targets(path)
            if target.startswith(forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_only_the_api_layer_builds_http_exceptions(self):
        offenders = [
            _rel(path)
            for path in IDENTITY.rglob("*.py")
            if "HTTPException" in path.read_text(encoding="utf-8-sig")
            and path.relative_to(IDENTITY).parts[0] != "api"
        ]
        self.assertEqual(offenders, [])

    def test_only_the_composition_root_reaches_foreign_legacy_internals(self):
        legacy = ("app.services", "app.models", "app.schemas")
        offenders = [
            f"{_rel(path)}: {target}"
            for path in IDENTITY.rglob("*.py")
            if path.name != "wiring.py"
            for target in _targets(path)
            if target.startswith(legacy)
        ]
        self.assertEqual(offenders, [])


class IdentityPublicSurfaceTests(unittest.TestCase):
    def test_public_exports_no_service_factory_dependency_or_orm(self):
        from app.modules.identity import public

        self.assertEqual(FORBIDDEN_EXPORTS & set(public.__all__), set())
        for name in sorted(FORBIDDEN_EXPORTS):
            with self.subTest(name=name):
                self.assertFalse(hasattr(public, name), name)
                with self.assertRaises(ImportError):
                    exec(f"from app.modules.identity.public import {name}", {})

    def test_public_has_no_lazy_attribute_hook_that_could_leak_internals(self):
        source = (IDENTITY / "public.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("def __getattr__", source)

    def test_public_exposes_the_documented_facades_and_dtos(self):
        from app.modules.identity import public

        for name in (
            "IdentityFacade",
            "IdentityAdminFacade",
            "TenantDirectory",
            "MembershipDirectory",
            "FeatureFlags",
            "TenantLifecycle",
            "AccessAudit",
            "TenantView",
            "UserView",
            "MembershipView",
            "FeatureGrantView",
            "AdminMembershipView",
            "PasswordResetResult",
            "AuthContext",
        ):
            self.assertIn(name, public.__all__)

    def test_password_reset_result_is_frozen_and_does_not_print_the_ticket_url(self):
        from app.modules.identity.public import PasswordResetResult

        result = PasswordResetResult(True, "ok", ticket_url="https://auth.example/ticket/SECRET")
        self.assertNotIn("SECRET", repr(result))
        self.assertTrue(PasswordResetResult.__dataclass_params__.frozen)

    def test_http_dependencies_are_imported_only_by_http_layers(self):
        offenders = []
        for path in APP.rglob("*.py"):
            rel = _rel(path)
            if rel.startswith("modules/identity/"):
                continue
            if "app.modules.identity.api.deps" not in _targets(path):
                continue
            parts = rel.split("/")
            is_http_layer = parts[0] == "api" or (parts[0] == "modules" and len(parts) > 2 and parts[2] == "api")
            if not is_http_layer:
                offenders.append(rel)
        self.assertEqual(offenders, [])


class IdentityOrmOwnershipTests(unittest.TestCase):
    def test_user_membership_audit_and_grant_orm_never_leave_identity(self):
        offenders = []
        for path in list(APP.rglob("*.py")) + list((BACKEND / "scripts").rglob("*.py")):
            rel = path.relative_to(BACKEND).as_posix()
            if rel.startswith("app/modules/identity/") or rel == "app/models/__init__.py":
                continue
            leaked = _orm_reads(path) - {"Tenant"}
            if leaked:
                offenders.append(f"{rel}: {sorted(leaked)}")
        self.assertEqual(offenders, [])

    def test_migrated_modules_have_no_runtime_identity_orm_imports(self):
        offenders = []
        for module in MIGRATED_MODULES:
            for path in (APP / "modules" / module).rglob("*.py"):
                if "app.modules.identity.infrastructure.models" in _targets(path) or _orm_reads(path):
                    offenders.append(_rel(path))
        self.assertEqual(offenders, [])

    def test_tenant_direct_readers_are_exactly_the_documented_legacy_files(self):
        readers = set()
        for path in APP.rglob("*.py"):
            rel = _rel(path)
            if rel.startswith("modules/identity/") or rel == "models/__init__.py":
                continue
            if "Tenant" in _orm_reads(path):
                readers.add(rel)
        self.assertEqual(readers, set(TENANT_DIRECT_READERS))
        for reason in TENANT_DIRECT_READERS.values():
            self.assertIn("future", reason)

    def test_external_code_never_writes_identity_state_fields(self):
        offenders = []
        for path in APP.rglob("*.py"):
            rel = _rel(path)
            if rel.startswith("modules/identity/"):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                    targets = [node.target]
                else:
                    continue
                for target in targets:
                    if not isinstance(target, ast.Attribute):
                        continue
                    base = ast.unparse(target.value).split(".")[-1]
                    owned_by_identity = base in {"user", "membership", "tenant", "grant"} and target.attr in {
                        "status",
                        "role",
                        "enabled",
                        "limits_json",
                        "is_internal",
                    }
                    if target.attr == "external_auth_id" or owned_by_identity:
                        offenders.append(f"{rel}:{node.lineno} {ast.unparse(target)}")
        self.assertEqual(offenders, [])

    def test_no_legacy_shims_for_identity(self):
        for relative in ("models/identity.py", "api/auth/deps.py", "services/identity_service.py"):
            self.assertFalse((APP / relative).exists(), relative)
        for path in APP.rglob("*.py"):
            self.assertNotIn("TEMPORARY compatibility shim", path.read_text(encoding="utf-8-sig"), str(path))


if __name__ == "__main__":
    unittest.main()
