"""Architecture tests of the Analytics module: layers, public surface, ORM ownership, mappers."""

from __future__ import annotations

import ast
import dataclasses
import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

BACKEND = Path(__file__).parent
APP = BACKEND / "app"
ANALYTICS = APP / "modules" / "analytics"
MODELS = "app.modules.analytics.infrastructure.models"
TABLES = {"agents", "calls", "call_events", "metric_snapshots_daily"}
# Non-production tooling that seeds Analytics rows directly in a staging database.
ORM_TOOLING_ALLOWLIST = {"scripts/seed_staging_analytics.py": "staging seed tool (writes fixtures, never imported by the app)"}
# The only modules outside Analytics that may name Analytics code, and what they may name.
EXTERNAL_ALLOWED = {
    "app.modules.analytics.public",
    "app.modules.analytics.api",  # app.main mounts api.dashboard_router
}
KNOWN_SHIMS: set[str] = set()
LEGACY_FILES = (
    "models/analytics.py",
    "services/call_persistence_service.py",
    "services/call_status_normalizer.py",
    "services/dashboard_analytics_service.py",
    "services/voice_call_projection_service.py",
    "api/endpoints/dashboard.py",
)


def _targets(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def _foreign_module(target: str) -> str | None:
    parts = target.split(".")
    if len(parts) >= 3 and parts[:2] == ["app", "modules"] and parts[2] != "analytics":
        return parts[2]
    return None


class AnalyticsLayerTests(unittest.TestCase):
    def test_domain_is_pure(self):
        forbidden = ("sqlalchemy", "fastapi", "starlette", "pydantic", "httpx", "app.models", "app.services", "app.api", "app.schemas", "app.db", "app.core")
        offenders = []
        for path in (ANALYTICS / "domain").rglob("*.py"):
            for target in _targets(path):
                other_layer = target.startswith("app.modules.analytics.") and not target.startswith("app.modules.analytics.domain")
                if target.startswith(forbidden) or other_layer or _foreign_module(target):
                    offenders.append(f"{_rel(path)}: {target}")
        self.assertEqual(offenders, [])

    def test_contracts_are_framework_free(self):
        forbidden = ("sqlalchemy", "fastapi", "starlette", "pydantic", "app.models", "app.services", "app.schemas")
        offenders = [t for t in _targets(ANALYTICS / "contracts.py") if t.startswith(forbidden) or _foreign_module(t)]
        self.assertEqual(offenders, [])

    def test_application_has_no_http_schema_or_foreign_dependency(self):
        forbidden = ("fastapi", "starlette", "pydantic", "app.schemas", "app.services", "app.models", "app.api",
                     "app.modules.analytics.api", "app.modules.analytics.wiring")
        offenders = [
            f"{_rel(path)}: {target}"
            for path in (ANALYTICS / "application").rglob("*.py")
            for target in _targets(path)
            if target.startswith(forbidden) or _foreign_module(target)
        ]
        self.assertEqual(offenders, [])

    def test_application_never_builds_http_exceptions(self):
        offenders = [
            _rel(path)
            for path in ANALYTICS.rglob("*.py")
            if "HTTPException" in path.read_text(encoding="utf-8-sig") and path.relative_to(ANALYTICS).parts[0] != "api"
        ]
        self.assertEqual(offenders, [])

    def test_only_wiring_and_api_reach_foreign_modules_and_only_through_public(self):
        offenders = []
        for path in ANALYTICS.rglob("*.py"):
            layer = path.relative_to(ANALYTICS).parts[0]
            for target in _targets(path):
                foreign = _foreign_module(target)
                if foreign is None:
                    continue
                public_only = target.endswith(".public") or target.startswith(f"app.modules.{foreign}.public.")
                http_deps = target.startswith("app.modules.identity.api.deps")
                if path.name == "wiring.py" and public_only:
                    continue
                if layer == "api" and (public_only or http_deps):
                    continue
                offenders.append(f"{_rel(path)}: {target}")
        self.assertEqual(offenders, [])

    def test_only_api_imports_http_schemas_and_framework(self):
        offenders = [
            _rel(path)
            for path in ANALYTICS.rglob("*.py")
            if path.relative_to(ANALYTICS).parts[0] != "api"
            and any(t.startswith(("fastapi", "pydantic", "app.schemas")) for t in _targets(path))
        ]
        self.assertEqual(offenders, [])


class AnalyticsPublicSurfaceTests(unittest.TestCase):
    def test_public_import_is_light(self):
        code = (
            "import json,sys; import app.modules.analytics.public; "
            "print(json.dumps(sorted(x for x in sys.modules if x == 'sqlalchemy' or x.startswith(("
            "'sqlalchemy.orm','fastapi','pydantic','app.modules.analytics.application',"
            "'app.modules.analytics.infrastructure','app.modules.analytics.api','app.modules.analytics.wiring',"
            "'app.modules.crm','app.modules.voice','app.modules.agents','app.modules.billing',"
            "'app.modules.identity','app.models')))))"
        )
        result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout.strip().splitlines()[-1]), [])

    def test_public_does_not_import_sqlalchemy_or_orm(self):
        offenders = [t for t in _targets(ANALYTICS / "public.py") if t.startswith(("sqlalchemy", MODELS, "app.models"))]
        self.assertEqual(offenders, [])

    def test_public_exports_facades_and_no_orm_or_service(self):
        from app.modules.analytics import public

        for name in ("AnalyticsCallLedger", "CallLookup", "AnalyticsAgentDirectory", "AnalyticsUsageFacts",
                     "AnalyticsDashboard", "AnalyticsMaintenance", "VoiceCallProjectionFacade", "AnalyticsCallMetrics"):
            self.assertIn(name, public.__all__)
        for name in ("Agent", "Call", "CallEvent", "MetricSnapshotDaily", "AnalyticsCallService",
                     "AnalyticsDashboardService", "VoiceCallProjectionService"):
            self.assertNotIn(name, public.__all__)
            self.assertFalse(hasattr(public, name), name)

    def test_contract_dataclasses_are_frozen(self):
        contracts = importlib.import_module("app.modules.analytics.contracts")
        classes = [c for c in vars(contracts).values() if dataclasses.is_dataclass(c) and c.__module__ == contracts.__name__]
        self.assertGreater(len(classes), 15)
        self.assertEqual([c.__name__ for c in classes if not c.__dataclass_params__.frozen], [])

    def test_no_public_method_commits_implicitly_without_a_commit_flag(self):
        source = (ANALYTICS / "public.py").read_text(encoding="utf-8-sig")
        self.assertNotIn(".commit(", source)


class AnalyticsOwnershipTests(unittest.TestCase):
    def test_four_tables_are_declared_once_in_the_module(self):
        import app.models  # noqa: F401  (register every ORM table)
        from app.db.base import Base

        declared = {
            mapper.local_table.name: mapper.class_.__module__
            for mapper in Base.registry.mappers
            if mapper.local_table.name in TABLES
        }
        self.assertEqual(set(declared), TABLES)
        self.assertEqual(set(declared.values()), {MODELS})

    def test_legacy_files_and_shims_are_gone(self):
        for relative in LEGACY_FILES:
            self.assertFalse((APP / relative).exists(), relative)
        self.assertEqual(KNOWN_SHIMS, set())
        for path in APP.rglob("*.py"):
            self.assertNotIn("TEMPORARY compatibility shim", path.read_text(encoding="utf-8-sig"), str(path))

    def test_nothing_outside_analytics_imports_its_internals(self):
        offenders = []
        for path in list(APP.rglob("*.py")) + list((BACKEND / "scripts").rglob("*.py")):
            rel = path.relative_to(BACKEND).as_posix()
            if rel.startswith("app/modules/analytics/") or rel in ORM_TOOLING_ALLOWLIST:
                continue
            for target in _targets(path):
                if target == "app.models.analytics":
                    offenders.append(f"{rel}: {target}")
                elif target.startswith("app.modules.analytics.") and not any(
                    target == allowed or target.startswith(allowed + ".") for allowed in EXTERNAL_ALLOWED
                ):
                    if rel == "app/models/__init__.py" and target.startswith(MODELS):
                        continue
                    offenders.append(f"{rel}: {target}")
        self.assertEqual(offenders, [])

    def test_orm_tooling_allowlist_is_exact(self):
        users = set()
        for path in (BACKEND / "scripts").rglob("*.py"):
            if any(t.startswith(MODELS) for t in _targets(path)):
                users.add(path.relative_to(BACKEND).as_posix())
        self.assertEqual(users, set(ORM_TOOLING_ALLOWLIST))

    def test_billing_identity_crm_voice_consume_only_the_public_api(self):
        for module in ("billing", "identity", "crm", "voice", "telephony"):
            for path in (APP / "modules" / module).rglob("*.py"):
                bad = [t for t in _targets(path) if t.startswith("app.modules.analytics.") and t != "app.modules.analytics.public"
                       and not t.startswith("app.modules.analytics.public.")]
                self.assertEqual(bad, [], str(path))

    def test_orm_does_not_navigate_to_tenant_and_keeps_internal_relationships(self):
        from sqlalchemy import inspect

        import app.models  # noqa: F401
        from app.modules.analytics.infrastructure.models import (
            Agent,
            Call,
            CallEvent,
            MetricSnapshotDaily,
        )

        expected = {
            Agent: {"calls", "metric_snapshots"},
            Call: {"agent", "events"},
            CallEvent: {"call"},
            MetricSnapshotDaily: {"agent"},
        }
        for model, relationships in expected.items():
            with self.subTest(model=model.__name__):
                self.assertEqual({r.key for r in inspect(model).relationships}, relationships)
                self.assertEqual(
                    [fk.target_fullname for fk in model.__table__.c.tenant_id.foreign_keys], ["tenants.id"]
                )

    def test_shared_kernel_mixins_are_used_instead_of_local_copies(self):
        source = (ANALYTICS / "infrastructure" / "models.py").read_text(encoding="utf-8-sig")
        self.assertIn("from app.db.mixins import", source)
        self.assertNotIn("class TimestampMixin", source)
        self.assertNotIn("def _uuid", source)


if __name__ == "__main__":
    unittest.main()
