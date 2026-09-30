"""Architecture tests for the modular monolith (docs/architecture/).

Static AST analysis of every import under app/ -- including function-local
imports, excluding `if TYPE_CHECKING:` blocks -- so the rules hold without a
database or any new dependency. Adding an exception here is an architecture
decision: document it in docs/architecture/MODULE_DEPENDENCIES.md first.
"""

from __future__ import annotations

import ast
import importlib
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

APP = Path(__file__).resolve().parent / "app"
SHIM_MARKER = "TEMPORARY compatibility shim"

# Legacy (not yet migrated) modules Tool Platform may still import directly.
# Each is shared infrastructure or a module without a public API yet.
TOOLS_LEGACY_ALLOWED = {
    "app.api.auth.deps",  # shared security: AuthContext / roles
    "app.core.config",  # shared settings
    "app.db.base",
    "app.db.mixins",
    "app.db.session",
    "app.services.integration_event_service",  # shared audit trail (tenant_integration_events)
    "app.services.secret_manager_service",  # shared encryption (Fernet)
    "app.services.tenant_feature_service",  # identity feature flags -- pending identity.public
}

# Paths moved into app.modules.tools; only their shims may still live there.
LEGACY_TOOL_PATHS = {
    "app.domain.tool_registry": "app.modules.tools.domain.registry",
    "app.domain.tool_schema": "app.modules.tools.domain.schema",
    "app.domain.tool_namespace": "app.modules.tools.domain.namespace",
    "app.domain.resolved_tool": "app.modules.tools.domain.resolved_tool",
    "app.domain.platform_tool_invocation": "app.modules.tools.domain.invocation",
    "app.domain.tool_mapping": "app.modules.tools.domain.mapping",
    "app.core.tool_http_limits": "app.modules.tools.domain.limits",
    "app.services.tool_resolver_service": "app.modules.tools.application.resolver",
    "app.services.tool_dispatch_service": "app.modules.tools.application.dispatcher",
    "app.services.platform_tool_contract_service": "app.modules.tools.application.contracts",
    "app.services.tool_catalog_service": "app.modules.tools.application.catalog",
    "app.services.tenant_tool_service": "app.modules.tools.application.tenant_tools",
    "app.services.custom_http_tool_executor": "app.modules.tools.infrastructure.http_executor",
    "app.services.tenant_tool_credential_service": "app.modules.tools.infrastructure.credentials",
    "app.services.tool_http_safety": "app.modules.tools.infrastructure.http_safety",
    "app.models.tools": "app.modules.tools.infrastructure.models",
    "app.schemas.tools_custom": "app.modules.tools.api.schemas",
    "app.api.endpoints.tools_custom": "app.modules.tools.api.router",
}


def _module_name(path: Path) -> str:
    parts = path.relative_to(APP.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _is_type_checking(node: ast.If) -> bool:
    test = node.test
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_imports(tree: ast.AST) -> set[str]:
    found: set[str] = set()

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.If) and _is_type_checking(node):
            for child in node.orelse:
                visit(child)
            return
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            # `from app.modules.x import public` imports the submodule app.modules.x.public
            for alias in node.names:
                candidate = f"{node.module}.{alias.name}"
                if (APP.parent / (candidate.replace(".", "/") + ".py")).exists():
                    found.add(candidate)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return {name for name in found if name == "app" or name.startswith("app.")}


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _graph() -> dict[str, tuple[Path, set[str]]]:
    return {
        _module_name(path): (path, _runtime_imports(ast.parse(_source(path))))
        for path in APP.rglob("*.py")
    }


def _owner(module: str) -> str | None:
    parts = module.split(".")
    return parts[2] if len(parts) > 2 and parts[:2] == ["app", "modules"] else None


def _is_public(module: str) -> bool:
    parts = module.split(".")
    return len(parts) == 4 and parts[3] == "public"


class ModuleBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.graph = _graph()

    def _violations(self, predicate) -> list[str]:
        return sorted(
            f"{source} -> {target}"
            for source, (_, targets) in self.graph.items()
            for target in targets
            if predicate(source, target)
        )

    def test_modules_only_import_other_modules_through_public(self) -> None:
        violations = self._violations(
            lambda s, t: _owner(s) is not None
            and _owner(t) is not None
            and _owner(s) != _owner(t)
            and not _is_public(t)
        )
        self.assertEqual(violations, [], "Cross-module imports must target app.modules.<name>.public")

    def test_legacy_code_only_imports_modules_through_public(self) -> None:
        # Composition-root exceptions: main.py mounts routers and
        # app/models/__init__.py registers ORM tables for Alembic.
        def allowed(source: str, target: str) -> bool:
            if _is_public(target) or _owner(target) is None:
                return True
            if source == "app.main" and target.startswith(f"app.modules.{_owner(target)}.api"):
                return True
            if source == "app.models" and target.endswith(".infrastructure.models"):
                return True
            path, _ = self.graph[source]
            return SHIM_MARKER in _source(path)

        violations = self._violations(lambda s, t: _owner(s) is None and not allowed(s, t))
        self.assertEqual(violations, [], "Code outside app.modules must use app.modules.<name>.public")

    def test_tools_does_not_import_other_domains_legacy_internals(self) -> None:
        violations = self._violations(
            lambda s, t: _owner(s) == "tools"
            and _owner(t) is None
            and t not in TOOLS_LEGACY_ALLOWED
        )
        self.assertEqual(violations, [], "Tool Platform must reach other domains via their public API or a port")

    def test_tools_domain_layer_is_pure(self) -> None:
        def violates(source: str, target: str) -> bool:
            if not source.startswith("app.modules.tools.domain"):
                return False
            if target.startswith("app.modules.tools."):
                return not target.startswith("app.modules.tools.domain")
            return target != "app.modules.voice.public"  # SessionContextV1 is part of the invocation contract

        self.assertEqual(self._violations(violates), [])

    def test_tools_application_does_not_depend_on_api_layer(self) -> None:
        violations = self._violations(
            lambda s, t: s.startswith("app.modules.tools.application") and t.startswith("app.modules.tools.api.router")
        )
        self.assertEqual(violations, [])

    def test_dispatcher_reaches_side_effecting_domains_only_through_ports(self) -> None:
        _, targets = self.graph["app.modules.tools.application.dispatcher"]
        forbidden = {t for t in targets if _owner(t) in {"crm", "scheduling", "integrations"}}
        self.assertEqual(forbidden, set(), "Wire CRM/Scheduling/Messaging in app.modules.tools.wiring, not the dispatcher")

    def test_no_production_code_uses_legacy_tool_paths(self) -> None:
        violations = []
        for source, (path, targets) in self.graph.items():
            if SHIM_MARKER in _source(path):
                continue
            violations += [f"{source} -> {t}" for t in targets & LEGACY_TOOL_PATHS.keys()]
        self.assertEqual(sorted(violations), [], "Import from app.modules.tools.public instead of legacy paths")

    def test_legacy_tool_paths_are_aliases_not_copies(self) -> None:
        for legacy, new in LEGACY_TOOL_PATHS.items():
            with self.subTest(legacy=legacy):
                self.assertIs(importlib.import_module(legacy), importlib.import_module(new))

    def test_import_graph_inside_tools_is_acyclic(self) -> None:
        tools = {m: {t for t in ts if t in self.graph and _owner(t) == "tools"} for m, (_, ts) in self.graph.items() if _owner(m) == "tools"}
        visiting, done = set(), set()

        def visit(node: str, trail: list[str]) -> None:
            if node in done:
                return
            self.assertNotIn(node, visiting, f"import cycle: {' -> '.join(trail + [node])}")
            visiting.add(node)
            for nxt in tools.get(node, ()):
                visit(nxt, trail + [node])
            visiting.discard(node)
            done.add(node)

        for module in tools:
            visit(module, [])


class ToolPortsTests(unittest.TestCase):
    """The dispatcher's platform handlers only talk to ToolPorts, so plain
    fakes are enough to exercise them -- no DB, no CRM/Scheduling services."""

    def setUp(self) -> None:
        from app.modules.tools.application import dispatcher
        from app.modules.tools.application.ports import ToolPorts
        from app.modules.tools.domain.invocation import PlatformToolInvocation
        from app.modules.voice.public import SessionContextV1

        self.dispatcher = dispatcher
        self.calls: list[tuple] = []
        calls = self.calls

        class Scheduling:
            def get_available_slots(self, **kw):
                calls.append(("slots", kw))
                return {"slots": []}

            def create_lead_booking(self, **kw):
                calls.append(("booking", kw))
                return SimpleNamespace(id="b1", status="pending", start_at=datetime(2026, 1, 1, 10, tzinfo=UTC))

        class Crm:
            def get_or_create_open_lead(self, **kw):
                calls.append(("lead", kw))
                return SimpleNamespace(id="c1"), SimpleNamespace(id="l1", status="new")

        class Sessions:
            def enrich_context(self, session, **kw):
                calls.append(("enrich", kw["event_source"]))

        self.ports = ToolPorts(scheduling=Scheduling(), crm=Crm(), messaging=None, sessions=Sessions())
        self.invocation = lambda args, ctx: PlatformToolInvocation(
            llm_args=args, context=SessionContextV1.model_validate(ctx), config={}
        )

    def test_create_lead_uses_trusted_caller_phone_and_enriches_session(self) -> None:
        handler = self.dispatcher._HANDLERS["crm.create_lead"]
        invocation = self.invocation({"name": "Ana", "phone": "+10000000000"}, {"caller": {"phone": "+573000000000"}})
        result = handler(None, self.ports, "t1", invocation, object())
        self.assertEqual(result, {"lead_id": "l1", "contact_id": "c1", "status": "new"})
        self.assertEqual(self.calls[0][1]["phone"], "+573000000000")
        self.assertEqual(self.calls[1], ("enrich", "crm.create_lead"))

    def test_create_booking_takes_lead_from_context_never_from_llm(self) -> None:
        handler = self.dispatcher._HANDLERS["calendar.create_booking"]
        invocation = self.invocation(
            {"start": "2026-01-01T10:00:00Z", "lead_id": "llm-lead"}, {"lead": {"id": "ctx-lead"}}
        )
        result = handler(None, self.ports, "t1", invocation, object())
        self.assertEqual(self.calls[0][1]["lead_id"], "ctx-lead")
        self.assertEqual(result["booking_id"], "b1")

    def test_create_booking_without_lead_context_fails_closed(self) -> None:
        handler = self.dispatcher._HANDLERS["calendar.create_booking"]
        with self.assertRaisesRegex(self.dispatcher.ToolExecutionError, "lead_context_required"):
            handler(None, self.ports, "t1", self.invocation({"start": "x"}, {}), object())
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
