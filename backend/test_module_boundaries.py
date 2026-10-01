"""Architecture tests for the modular monolith (docs/architecture/).

Static AST analysis of every import under app/ -- including function-local
imports, excluding `if TYPE_CHECKING:` blocks -- so the rules hold without a
database or any new dependency. Adding an exception here is an architecture
decision: document it in docs/architecture/MODULE_DEPENDENCIES.md first.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import typing
import unittest
from collections.abc import Mapping
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
}

# Legacy (not yet migrated) modules Agent Builder may still import directly.
AGENTS_LEGACY_ALLOWED = {
    "app.api.auth.deps",  # shared security: AuthContext / roles
    "app.db.base",
    "app.db.mixins",
    "app.db.session",
    "app.schemas.runtime_session",  # RuntimeSessionSpecV1: shared runtime contract (Voice <-> voice-runtime)
    "app.services.integration_event_service",  # shared audit trail (tenant_integration_events)
}

# Provider implementations (Voice Legacy / Ultravox). Agent Builder must
# reach them only through VoiceProviderPort -> voice.public, and they must
# never reach back into Agent Builder.
PROVIDER_IMPLEMENTATIONS = ("app.services.ultravox_", "app.services.voice_provider_admin")


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


def _strongly_connected(graph: dict[str, tuple[Path, set[str]]]) -> list[set[str]]:
    """Tarjan, iterative (the app graph is too deep for recursion)."""
    edges = {m: [t for t in targets if t in graph and t != m] for m, (_, targets) in graph.items()}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []
    counter = 0
    for root, root_edges in edges.items():
        if root in index:
            continue
        work = [(root, iter(root_edges))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            child = next(children, None)
            if child is not None:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(edges[child])))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = set()
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.add(member)
                    if member == node:
                        break
                if len(component) > 1:
                    components.append(component)
    return components


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

    def test_every_app_import_in_backend_resolves(self) -> None:
        # Catches stale imports of retired paths in any form -- including
        # `from app.domain import tool_registry`, which a dotted-path grep
        # misses -- across app/ and every test module.
        problems = set()
        for path in [*APP.rglob("*.py"), *APP.parent.glob("test_*.py")]:
            for node in ast.walk(ast.parse(_source(path))):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith("app"):
                    pairs = [(node.module, alias.name) for alias in node.names if alias.name != "*"]
                elif isinstance(node, ast.Import):
                    pairs = [(alias.name, None) for alias in node.names if alias.name.startswith("app")]
                else:
                    continue
                for module_name, name in pairs:
                    try:
                        module = importlib.import_module(module_name)
                    except ImportError:
                        problems.add(f"{path.name}: {module_name}")
                        continue
                    if name and not hasattr(module, name):
                        try:
                            importlib.import_module(f"{module_name}.{name}")
                        except ImportError:
                            problems.add(f"{path.name}: {module_name}.{name}")
        self.assertEqual(sorted(problems), [])

    # -- Agent Builder --------------------------------------------------------

    def test_agents_does_not_import_other_domains_legacy_internals(self) -> None:
        violations = self._violations(
            lambda s, t: _owner(s) == "agents" and _owner(t) is None and t not in AGENTS_LEGACY_ALLOWED
        )
        self.assertEqual(violations, [], "Agent Builder must reach other domains via their public API or a port")

    def test_agents_never_imports_a_voice_provider_implementation(self) -> None:
        # Function-level (lazy) imports count too: this is the rule that used
        # to be broken by AgentService -> UltravoxAdminService.
        violations = self._violations(lambda s, t: _owner(s) == "agents" and t.startswith(PROVIDER_IMPLEMENTATIONS))
        self.assertEqual(violations, [], "Use VoiceProviderPort (wired to voice.public), never a provider adapter")

    def test_voice_provider_implementations_never_import_agent_builder(self) -> None:
        # The reverse edge of the old cycle (UltravoxAdminService ->
        # AgentService) and any other way back into Agent Builder.
        violations = self._violations(
            lambda s, t: s.startswith(PROVIDER_IMPLEMENTATIONS) and _owner(t) == "agents"
        )
        self.assertEqual(violations, [], "Provider adapters describe remote agents; Agent Builder writes agents")

    def test_agent_service_ultravox_cycle_is_gone(self) -> None:
        service = "app.modules.agents.application.service"
        _, service_targets = self.graph[service]
        self.assertFalse({t for t in service_targets if t.startswith(PROVIDER_IMPLEMENTATIONS)})
        for module, (_, targets) in self.graph.items():
            if module.startswith(PROVIDER_IMPLEMENTATIONS):
                self.assertNotIn(service, targets, module)

    def test_provider_implementations_import_no_module_at_runtime(self) -> None:
        # Adapters return their own models; voice_providers.public translates
        # them. Annotations may use TYPE_CHECKING imports.
        violations = self._violations(
            lambda s, t: s.startswith(PROVIDER_IMPLEMENTATIONS) and _owner(t) is not None
        )
        self.assertEqual(violations, [])

    def test_no_import_cycle_links_agent_builder_and_a_provider_implementation(self) -> None:
        # Strongly connected components of the whole import graph, lazy
        # imports included: Agents may reach a provider adapter (through its
        # port), but no path may lead back -- not even transitively.
        offending = [
            sorted(component)
            for component in _strongly_connected(self.graph)
            if any(_owner(m) == "agents" for m in component)
            and any(m.startswith(PROVIDER_IMPLEMENTATIONS) for m in component)
        ]
        self.assertEqual(offending, [])

    def test_agents_domain_layer_is_pure(self) -> None:
        def violates(source: str, target: str) -> bool:
            if not source.startswith("app.modules.agents.domain"):
                return False
            if target.startswith("app.modules.agents."):
                return not target.startswith("app.modules.agents.domain")
            return target != "app.modules.voice_providers.public"  # voice registry compatibility rules

        self.assertEqual(self._violations(violates), [])

    def test_agents_application_does_not_depend_on_api_layer_at_runtime(self) -> None:
        violations = self._violations(
            lambda s, t: s.startswith("app.modules.agents.application") and t.startswith("app.modules.agents.api")
        )
        self.assertEqual(violations, [], "HTTP request types may only be imported under TYPE_CHECKING")

    def test_no_code_navigates_removed_cross_module_relationships(self) -> None:
        # VoiceSession.agent / .agent_version and
        # TenantAgentVersion.voice_agent_config no longer exist as ORM
        # relationships; the owners' public APIs replace them.
        found = []
        for path in APP.rglob("*.py"):
            for node in ast.walk(ast.parse(_source(path))):
                if isinstance(node, ast.Attribute) and node.attr in {"agent_version", "voice_agent_config"}:
                    found.append(f"{_module_name(path)}:{node.lineno} .{node.attr}")
        self.assertEqual(found, [])

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


# Attributes of other modules' ORM rows Tool Platform used to navigate.
# Reading them again would mean an ORM object crossed the boundary.
FOREIGN_ORM_ATTRIBUTES = {"agent_version", "session_context_json", "runtime_binding_json", "_row"}

# Cross-module APIs that must speak DTOs only (no ORM rows, no bare Any).
CRITICAL_PUBLIC_APIS = {
    "app.modules.voice.public": ["VoiceSessionFacade"],
    "app.modules.voice_providers.public": ["VoiceProviderFacade"],
    "app.modules.crm.public": ["CrmFacade"],
    "app.modules.integrations.public": ["WhatsAppFacade"],
    "app.modules.scheduling.public": ["SchedulingFacade"],

    "app.modules.identity.public": ["FeatureFlags"],
    "app.modules.voice_legacy.public": ["VoiceLegacyFacade"],
    "app.modules.agents.public": ["AgentsFacade"],
    "app.modules.agents.application.ports": [
        "VoiceProviderPort",
        "LegacyVoicePort",
        "IntegrationReadinessPort",
        "VoiceSessionsPort",
    ],
    "app.modules.tools.application.ports": [
        "SchedulingToolPort",
        "CrmToolPort",
        "MessagingToolPort",
        "VoiceSessionToolPort",
    ],
}
PUBLIC_DTOS = {
    "app.modules.voice.public": ["ToolSessionView", "ToolBindingView"],
    "app.modules.voice_providers.public": [
        "ProviderToolRef",
        "ProviderAgentSnapshot",
        "ProviderVoiceSelection",
        "ProviderAgentImport",
    ],
    "app.modules.agents.public": ["AgentToolBindingView", "PublishedAgent", "AgentDisplay", "ImportedAgent"],
    "app.modules.voice_legacy.public": ["LegacyVoiceDefaults"],
    "app.modules.crm.public": ["ContactRef", "LeadRef"],
    "app.modules.integrations.public": ["WhatsAppTemplateContract", "WhatsAppSendOutcome"],
    "app.modules.scheduling.public": ["BookingSummary"],
}
# Genuinely dynamic payloads, not entities: free-text LLM argument.
ANY_ALLOWED = {("create_lead_booking", "notes")}


def _orm_base() -> type:
    from app.db.base import Base

    return Base


def _boundary_problems(annotation: object, where: str, base: type) -> list[str]:
    """ORM classes anywhere in the annotation, or Any used directly as a
    value (Any as the value type of a dict/Mapping payload is fine)."""
    if annotation is typing.Any:
        return [f"{where}: Any"]
    if isinstance(annotation, type) and issubclass(annotation, base):
        return [f"{where}: ORM {annotation.__name__}"]
    if isinstance(annotation, type) and "ultravox" in annotation.__module__:
        return [f"{where}: provider-specific {annotation.__name__}"]
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if isinstance(origin, type) and issubclass(origin, Mapping):
        args = args[:1] + tuple(a for a in args[1:] if a is not typing.Any)
    problems = []
    for arg in args:
        if arg is not Ellipsis:
            problems += _boundary_problems(arg, where, base)
    return problems


def _type_namespace(module) -> dict:
    """Module globals plus the names some public APIs only import under
    TYPE_CHECKING (to keep import-time dependencies light)."""
    from app.modules.voice_providers import public as voice_providers_public
    from app.schemas import runtime_session

    return {**vars(runtime_session), **vars(voice_providers_public), **vars(module)}


class DataBoundaryTests(unittest.TestCase):
    """Import rules alone let ORM rows travel through `Any`. These pin the
    data contract of the critical cross-module APIs."""

    def test_critical_public_apis_take_and_return_dtos_only(self) -> None:
        base, problems = _orm_base(), []
        for module_name, classes in CRITICAL_PUBLIC_APIS.items():
            module = importlib.import_module(module_name)
            for class_name in classes:
                cls = getattr(module, class_name)
                for name, member in vars(cls).items():
                    if name.startswith("_") or not callable(member):
                        continue
                    hints = typing.get_type_hints(member, _type_namespace(module))
                    for param, annotation in hints.items():
                        if (name, param) in ANY_ALLOWED:
                            continue
                        problems += _boundary_problems(annotation, f"{class_name}.{name}({param})", base)
        self.assertEqual(problems, [])

    def test_public_dtos_are_frozen_and_carry_no_orm(self) -> None:
        base, problems = _orm_base(), []
        for module_name, classes in PUBLIC_DTOS.items():
            module = importlib.import_module(module_name)
            for class_name in classes:
                cls = getattr(module, class_name)
                self.assertTrue(cls.__dataclass_params__.frozen, f"{class_name} must be frozen")
                hints = typing.get_type_hints(cls)  # resolved in the defining module
                for f in dataclasses.fields(cls):
                    problems += _boundary_problems(hints[f.name], f"{class_name}.{f.name}", base)
        self.assertEqual(problems, [])

    def test_tools_never_navigates_foreign_orm_attributes(self) -> None:
        found = []
        for path in (APP / "modules" / "tools").rglob("*.py"):
            for node in ast.walk(ast.parse(_source(path))):
                if isinstance(node, ast.Attribute) and node.attr in FOREIGN_ORM_ATTRIBUTES:
                    found.append(f"{_module_name(path)}:{node.lineno} .{node.attr}")
        self.assertEqual(found, [])

    def test_boundary_checker_detects_leaks(self) -> None:
        from app.models.crm import CrmLead

        base = _orm_base()
        self.assertTrue(_boundary_problems(tuple[typing.Any, CrmLead], "x", base))
        self.assertTrue(_boundary_problems(CrmLead | None, "x", base))
        from app.schemas.ultravox_admin import UltravoxAgentDetail

        self.assertTrue(_boundary_problems(tuple[UltravoxAgentDetail, ...], "x", base))
        self.assertFalse(_boundary_problems(dict[str, typing.Any], "x", base))


class ToolPortsTests(unittest.TestCase):
    """The dispatcher's platform handlers only talk to ToolPorts, so plain
    fakes are enough to exercise them -- no DB, no CRM/Scheduling services."""

    def setUp(self) -> None:
        from app.modules.crm.public import ContactRef, LeadRef
        from app.modules.tools.application import dispatcher
        from app.modules.tools.application.ports import ToolPorts
        from app.modules.tools.domain.invocation import PlatformToolInvocation
        from app.modules.voice.public import SessionContextV1, ToolSessionView

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
                return ContactRef(id="c1", tenant_id="t1"), LeadRef(id="l1", tenant_id="t1", contact_id="c1", status="new")

        class Sessions:
            def enrich_context(self, session_id, **kw):
                calls.append(("enrich", session_id, kw["contact"], kw["lead"], kw["event_source"]))

        self.ports = ToolPorts(scheduling=Scheduling(), crm=Crm(), messaging=None, sessions=Sessions())
        self.session = ToolSessionView(
            id="s1", tenant_id="t1", status="connected", agent_id="a1", agent_status="active",
            tool_bindings=(), context=SessionContextV1(),
        )
        self.invocation = lambda args, ctx: PlatformToolInvocation(
            llm_args=args, context=SessionContextV1.model_validate(ctx), config={}
        )

    def test_create_lead_uses_trusted_caller_phone_and_enriches_session_by_id_with_refs(self) -> None:
        from app.modules.crm.public import ContactRef, LeadRef

        handler = self.dispatcher._HANDLERS["crm.create_lead"]
        invocation = self.invocation({"name": "Ana", "phone": "+10000000000"}, {"caller": {"phone": "+573000000000"}})
        result = handler(None, self.ports, "t1", invocation, self.session)
        self.assertEqual(result, {"lead_id": "l1", "contact_id": "c1", "status": "new"})
        self.assertEqual(self.calls[0][1]["phone"], "+573000000000")
        _, session_id, contact, lead, source = self.calls[1]
        self.assertEqual((session_id, source), ("s1", "crm.create_lead"))
        self.assertIsInstance(contact, ContactRef)
        self.assertIsInstance(lead, LeadRef)

    def test_create_booking_takes_lead_from_context_never_from_llm(self) -> None:
        handler = self.dispatcher._HANDLERS["calendar.create_booking"]
        invocation = self.invocation(
            {"start": "2026-01-01T10:00:00Z", "lead_id": "llm-lead"}, {"lead": {"id": "ctx-lead"}}
        )
        result = handler(None, self.ports, "t1", invocation, self.session)
        self.assertEqual(self.calls[0][1]["lead_id"], "ctx-lead")
        self.assertEqual(result["booking_id"], "b1")

    def test_create_booking_without_lead_context_fails_closed(self) -> None:
        handler = self.dispatcher._HANDLERS["calendar.create_booking"]
        with self.assertRaisesRegex(self.dispatcher.ToolExecutionError, "lead_context_required"):
            handler(None, self.ports, "t1", self.invocation({"start": "x"}, {}), self.session)
        self.assertEqual(self.calls, [])

    def test_session_view_terminal_rules_match_previous_dispatch_guard(self) -> None:
        self.assertFalse(self.session.is_terminal)
        for changes in ({"status": "ended"}, {"agent_id": None}, {"agent_status": "archived"}):
            self.assertTrue(dataclasses.replace(self.session, **changes).is_terminal, changes)


if __name__ == "__main__":
    unittest.main()
