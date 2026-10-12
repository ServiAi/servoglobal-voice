from __future__ import annotations

import ast
import functools
import hashlib
import inspect
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

APP = Path(__file__).parent / "app"
MODULE = APP / "modules" / "voice_experiences"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _files(path: Path) -> list[Path]:
    return sorted(path.rglob("*.py"))


def _hides_implementation(annotation: object) -> bool:
    """True for ``Any`` / bare ``object`` / ``dict[str, Any]``-style escape hatches."""
    import typing

    if annotation is typing.Any or annotation is object:
        return True
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin is dict:  # JSON payloads may be ``dict[str, object]``; ``Any`` is never fine
        return any(arg is typing.Any for arg in args)
    return any(_hides_implementation(arg) for arg in args if arg is not type(None))


BASE_REF = os.environ.get("OPENAPI_BASE_REF", "origin/develop")
_SNAPSHOT_SCRIPT = """
import json, sys
sys.path.insert(0, '.')
import app.models  # noqa: F401
from app.main import app
from app.db.base import Base
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

print(json.dumps({"openapi": app.openapi(), "ddl": %s}, sort_keys=True, separators=(",", ":")))
""" % "__DDL_EXPR__"
_DDL_EXPR = (
    "{**{t.name: str(CreateTable(t).compile(dialect=postgresql.dialect())) for t in Base.metadata.tables.values()},"
    " **{'index:' + (i.name or ''): str(CreateIndex(i).compile(dialect=postgresql.dialect()))"
    " for t in Base.metadata.tables.values() for i in t.indexes}}"
)
_SNAPSHOT_SCRIPT = _SNAPSHOT_SCRIPT.replace("__DDL_EXPR__", _DDL_EXPR)


def _openapi_digest(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _ddl_snapshot() -> dict[str, str]:
    import app.models  # noqa: F401
    from app.db.base import Base
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex, CreateTable

    dialect = postgresql.dialect()
    return {
        **{t.name: str(CreateTable(t).compile(dialect=dialect)) for t in Base.metadata.tables.values()},
        **{
            "index:" + (i.name or ""): str(CreateIndex(i).compile(dialect=dialect))
            for t in Base.metadata.tables.values()
            for i in t.indexes
        },
    }


@functools.lru_cache(maxsize=1)
def _base_snapshot() -> dict:
    """The base ref's full OpenAPI and per-table DDL, produced by importing its ``app`` from
    ``git archive`` in this same environment (so dependency versions cannot create false diffs)."""
    repo = Path(__file__).resolve().parent.parent
    archive = subprocess.run(["git", "archive", BASE_REF, "backend/app"], cwd=repo, capture_output=True)
    if archive.returncode != 0:
        if os.environ.get("CI"):
            raise AssertionError(f"base ref {BASE_REF} unavailable in CI: {archive.stderr.decode()[:200]}")
        raise unittest.SkipTest(f"base ref {BASE_REF} not available locally")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-c", _SNAPSHOT_SCRIPT],
            cwd=Path(tmp) / "backend",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(f"base snapshot generation failed: {result.stderr[-500:]}")
    return json.loads(result.stdout.strip().splitlines()[-1])


class VoiceExperiencesBoundaryTests(unittest.TestCase):
    def test_module_layer_import_graph_has_no_scc_cycles(self) -> None:
        layers = ("domain", "application", "infrastructure", "api", "wiring", "public")
        prefix = "app.modules.voice_experiences."
        graph = {layer: set() for layer in layers}
        for layer in layers[:4]:
            folder = MODULE / layer
            for path in _files(folder):
                for imported in _imports(path):
                    if not imported.startswith(prefix):
                        continue
                    target = imported.removeprefix(prefix).split(".", 1)[0]
                    if target in graph and target != layer:
                        graph[layer].add(target)
        graph["wiring"] = {
            target for imported in _imports(MODULE / "wiring.py")
            if imported.startswith(prefix)
            for target in (imported.removeprefix(prefix).split(".", 1)[0],)
            if target in graph and target != "wiring"
        }
        graph["public"] = {
            target for imported in _imports(MODULE / "public.py")
            if imported.startswith(prefix)
            for target in (imported.removeprefix(prefix).split(".", 1)[0],)
            if target in graph and target != "public"
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(layer: str) -> bool:
            if layer in visiting:
                return True
            if layer in visited:
                return False
            visiting.add(layer)
            if any(visit(target) for target in graph[layer]):
                return True
            visiting.remove(layer)
            visited.add(layer)
            return False

        self.assertFalse(any(visit(layer) for layer in graph), graph)

    def test_domain_and_application_keep_their_import_boundaries(self) -> None:
        domain_forbidden = (
            "fastapi", "starlette", "sqlalchemy", "app.schemas", "app.services",
            "app.models", "app.modules.voice_experiences.infrastructure",
            "app.modules.voice_experiences.api", "livekit", "ultravox", "httpx",
            "app.modules.crm.infrastructure", "app.modules.identity.infrastructure",
            "app.modules.voice.infrastructure", "app.modules.voice_legacy.infrastructure",
        )
        application_forbidden = (
            "fastapi", "starlette", "pydantic", "app.schemas", "app.services",
            "app.models", "app.modules.voice_experiences.api", "livekit", "ultravox",
            "httpx", "app.modules.crm.infrastructure", "app.modules.identity.infrastructure",
            "app.modules.integrations.infrastructure", "app.modules.telephony.infrastructure",
            "app.modules.voice.infrastructure", "app.modules.voice_legacy.infrastructure",
            "app.modules.voice_providers.infrastructure",
            "app.modules.agents.infrastructure",
        )
        for folder, forbidden in (
            (MODULE / "domain", domain_forbidden),
            (MODULE / "application", application_forbidden),
        ):
            for path in _files(folder):
                for imported in _imports(path):
                    with self.subTest(path=path.relative_to(APP), imported=imported):
                        self.assertFalse(
                            any(imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden),
                            f"forbidden import {imported} in {path.relative_to(APP)}",
                        )

    def test_domain_and_application_are_provider_neutral(self) -> None:
        for folder in (MODULE / "domain", MODULE / "application"):
            for path in _files(folder):
                source = path.read_text(encoding="utf-8").lower()
                with self.subTest(path=path.relative_to(APP)):
                    self.assertNotRegex(source, r"\b(?:ultravox|livekit)\b")

    def test_other_modules_use_only_the_public_voice_experiences_api(self) -> None:
        prefix = "app.modules.voice_experiences."
        for path in _files(APP / "modules"):
            if MODULE in path.parents:
                continue
            for imported in _imports(path):
                if imported.startswith(prefix):
                    with self.subTest(path=path.relative_to(APP), imported=imported):
                        self.assertEqual(imported, "app.modules.voice_experiences.public")

    def test_public_dtos_are_frozen_and_public_signatures_are_framework_free(self) -> None:
        import typing

        from app.modules.voice_experiences import public

        dtos = [
            value for value in vars(public).values()
            if is_dataclass(value) and value.__module__.startswith("app.modules.voice_experiences")
        ]
        self.assertGreaterEqual(len(dtos), 3)
        for dto in dtos:
            self.assertTrue(dto.__dataclass_params__.frozen, dto)
            hints = typing.get_type_hints(dto)
            for field in fields(dto):
                with self.subTest(dto=dto.__name__, field=field.name):
                    self.assertFalse(_hides_implementation(hints[field.name]), hints[field.name])
        self.assertEqual(
            typing.get_type_hints(public.VoiceContextFieldSnapshot)["options"],
            tuple[public.VoiceContextOptionSnapshot, ...],
        )

        callables = [
            (f"{name}", value) for name, value in vars(public).items()
            if inspect.isfunction(value) and value.__module__ == public.__name__
        ]
        for name, value in vars(public).items():
            if inspect.isclass(value) and getattr(value, "_is_protocol", False) and value.__module__ == public.__name__:
                callables.extend(
                    (f"{name}.{method}", member)
                    for method, member in vars(value).items()
                    if inspect.isfunction(member) and not method.startswith("_")
                )
        self.assertGreaterEqual(len(callables), 5)
        for name, function in callables:
            hints = typing.get_type_hints(function)
            self.assertIn("return", hints, name)
            for parameter, annotation in hints.items():
                with self.subTest(callable=name, parameter=parameter):
                    self.assertFalse(_hides_implementation(annotation), f"{name}: {annotation}")
                    rendered = str(annotation).lower()
                    for forbidden in ("sqlalchemy", "fastapi", "pydantic", "infrastructure"):
                        self.assertNotIn(forbidden, rendered)

    def test_public_factories_return_protocols_not_implementation_classes(self) -> None:
        import typing

        from app.modules.voice_experiences import public

        self.assertIs(
            typing.get_type_hints(public.create_callback_worker)["return"],
            public.VoiceCallbackWorkerPort,
        )
        self.assertIs(
            typing.get_type_hints(public.create_context_schema_reader)["return"],
            public.VoiceContextSchemaReader,
        )

    def test_public_module_source_imports_no_implementation_or_framework(self) -> None:
        forbidden = (
            "sqlalchemy", "fastapi", "starlette", "pydantic", "app.models", "app.services",
            "app.modules.voice_experiences.infrastructure", "app.modules.voice_experiences.application",
            "app.modules.voice_experiences.api",
        )
        tree = ast.parse((MODULE / "public.py").read_text(encoding="utf-8"))
        top_level = set()
        for node in tree.body:  # lazy imports inside factories are the composition seam
            if isinstance(node, ast.Import):
                top_level.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                top_level.add(node.module)
        for imported in top_level:
            self.assertFalse(
                any(imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden),
                imported,
            )

    def test_voice_experiences_entities_are_not_reexported_by_app_models(self) -> None:
        import app.models as legacy_models
        from app.modules.voice_experiences.infrastructure import models

        for name in models.__all__:
            with self.subTest(entity=name):
                self.assertNotIn(name, legacy_models.__all__)
                self.assertFalse(hasattr(legacy_models, name))
        from app.db.base import Base

        self.assertIn("tenant_voice_experience_submissions", Base.metadata.tables)

    def test_the_legacy_runtime_directory_is_gone_and_nothing_imports_it(self) -> None:
        self.assertFalse((MODULE / "infrastructure" / "legacy_runtime").exists())
        for path in _files(APP):
            for imported in _imports(path):
                with self.subTest(path=str(path.relative_to(APP)), imported=imported):
                    self.assertNotIn("legacy_runtime", imported)

    def test_public_import_does_not_load_implementation_layers(self) -> None:
        code = (
            "import sys, app.modules.voice_experiences.public; "
            "print(sorted(n for n in sys.modules if n.startswith(("
            "'sqlalchemy', 'fastapi', 'app.models', 'app.services', 'livekit', 'ultravox', "
            "'app.modules.voice_experiences.application', 'app.modules.voice_experiences.infrastructure', "
            "'app.modules.voice_experiences.api', 'app.modules.crm', 'app.modules.identity', "
            "'app.modules.voice.'))))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=APP.parent,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "[]")

    def test_voice_experiences_orm_relations_stay_inside_the_owner(self) -> None:
        from sqlalchemy import inspect as inspect_orm

        from app.modules.voice_experiences.infrastructure.models import (
            TenantVoiceContextField,
            TenantVoiceContextSchema,
            TenantVoiceContextSession,
            TenantVoiceExperience,
            TenantVoiceExperienceSubmission,
            TenantVoiceExperienceSubmissionValue,
            TenantVoiceExperienceVersion,
            TenantVoiceRuntimeCall,
            VoicePublicRateLimitWindow,
        )

        models = (
            TenantVoiceExperience,
            TenantVoiceExperienceVersion,
            TenantVoiceContextSchema,
            TenantVoiceContextField,
            TenantVoiceExperienceSubmission,
            TenantVoiceExperienceSubmissionValue,
            TenantVoiceContextSession,
            TenantVoiceRuntimeCall,
            VoicePublicRateLimitWindow,
        )
        for model in models:
            for relationship in inspect_orm(model).relationships:
                with self.subTest(model=model.__name__, relationship=relationship.key):
                    self.assertTrue(
                        relationship.mapper.class_.__module__.startswith(
                            "app.modules.voice_experiences."
                        )
                    )

    def test_ddl_is_unchanged_from_the_base(self) -> None:
        import app.models
        from app.db.base import Base
        from app.modules.voice_experiences.infrastructure import models as voice_models  # noqa: F401
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateIndex, CreateTable

        dialect = postgresql.dialect()
        tables = sorted(Base.metadata.tables.values(), key=lambda table: table.name)
        ddl = [str(CreateTable(table).compile(dialect=dialect)) for table in tables]
        ddl.extend(
            str(CreateIndex(index).compile(dialect=dialect))
            for table in tables
            for index in sorted(table.indexes, key=lambda item: item.name or "")
        )
        self.assertTrue(ddl)
        base, branch = _base_snapshot()["ddl"], _ddl_snapshot()
        changed = {key for key in base.keys() | branch.keys() if base.get(key) != branch.get(key)}
        # PR #137 retires the runtime, not the data: no table, column, constraint or index changes.
        self.assertEqual(changed, set())
        crm_calls = Base.metadata.tables["crm_voice_calls"]
        self.assertFalse(crm_calls.c.origin.nullable)
        self.assertIn("crm_outbound", str(crm_calls.c.origin.server_default.arg))
        self.assertIn("ck_crm_voice_calls_origin", {constraint.name for constraint in crm_calls.constraints})
        runtime_calls = Base.metadata.tables["tenant_voice_runtime_calls"]
        self.assertFalse(runtime_calls.c.launch_runtime.nullable)
        self.assertIsNone(runtime_calls.c.launch_runtime.default)  # no implicit canonical classification
        self.assertIn("legacy_provider", str(runtime_calls.c.launch_runtime.server_default.arg))
        self.assertIn(
            "ck_voice_runtime_launch_runtime",
            {constraint.name for constraint in runtime_calls.constraints},
        )
        self.assertTrue(runtime_calls.c.voice_session_id.nullable)
        self.assertEqual(
            {fk.name for fk in runtime_calls.c.voice_session_id.foreign_keys}, {"fk_voice_runtime_voice_session"}
        )
        self.assertEqual(
            {fk.ondelete for fk in runtime_calls.c.voice_session_id.foreign_keys}, {"RESTRICT"}
        )
        experiences = Base.metadata.tables["tenant_voice_experiences"]
        versions = Base.metadata.tables["tenant_voice_experience_versions"]
        self.assertFalse(experiences.c.agent_id.nullable)
        self.assertFalse(versions.c.agent_id.nullable)
        self.assertFalse(versions.c.agent_version_id.nullable)
        self.assertEqual(
            {index.name for index in experiences.indexes if index.name and "agent_id" in index.name},
            {"ix_tenant_voice_experiences_tenant_agent_id"},
        )
        self.assertEqual(
            {index.name for index in versions.indexes if index.name and "agent" in index.name},
            {
                "ix_tenant_voice_experience_versions_tenant_agent",
                "ix_tenant_voice_experience_versions_agent_version",
            },
        )
        self.assertEqual(
            {fk.name for fk in experiences.c.agent_id.foreign_keys},
            {"fk_tenant_voice_experiences_agent"},
        )
        self.assertEqual(
            {fk.name for fk in versions.c.agent_id.foreign_keys},
            {"fk_tenant_voice_experience_versions_agent"},
        )
        self.assertEqual(
            {fk.name for fk in versions.c.agent_version_id.foreign_keys},
            {"fk_tenant_voice_experience_versions_agent_version"},
        )

    def test_public_webrtc_path_uses_the_canonical_runtime_and_no_provider_or_legacy_code(self) -> None:
        forbidden = (
            "ultravox", "app.services", "app.models", "app.modules.voice_legacy",
            "app.modules.voice_providers", "app.modules.voice.application",
            "app.modules.voice.infrastructure", "app.modules.voice_experiences.infrastructure.legacy_runtime",
        )
        paths = [
            MODULE / "application" / "public_webrtc_service.py",
            MODULE / "application" / "ports.py",
            MODULE / "infrastructure" / "voice_runtime_adapter.py",
        ]
        for path in paths:
            for imported in _imports(path):
                with self.subTest(path=path.name, imported=imported):
                    self.assertFalse(
                        any(imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden),
                        imported,
                    )
            source = path.read_text(encoding="utf-8")
            for name in ("VoiceConfigService", "TenantVoiceProviderConfig", "TenantVoiceAgentConfig",
                         "VoiceExperienceRuntimeProvider", "VoiceLegacyFacade"):
                self.assertNotIn(name, source, f"{name} in {path.name}")

    def test_voice_experiences_reaches_voice_only_through_its_public_api(self) -> None:
        for path in _files(MODULE):
            for imported in _imports(path):
                if imported.startswith("app.modules.voice."):
                    with self.subTest(path=path.relative_to(APP), imported=imported):
                        self.assertEqual(imported, "app.modules.voice.public")

    def test_no_production_code_can_originate_a_call_through_the_ai_provider(self) -> None:
        forbidden = (
            "start_outbound_call", "VoiceSipRouteConfig", "VoiceClientConfig", "voice_client",
            "create_runtime_webhook_service", "VoiceRuntimeWebhookService", "start_lead_call",
            "LegacyCallbackWorker", "LegacyCallbackRequests", "PublicVoiceCallbackService",
            "PublicVoiceCallService", "VoiceExperienceRuntimeProvider", "VoiceCallbackWorker(",
        )
        for path in _files(APP):
            source = path.read_text(encoding="utf-8")
            for symbol in forbidden:
                with self.subTest(path=str(path.relative_to(APP)), symbol=symbol):
                    self.assertNotIn(symbol, source)

    def test_no_production_writer_creates_legacy_launches_or_legacy_callbacks(self) -> None:
        legacy_launch = re.compile(r"launch_runtime\s*=\s*[\"']legacy_provider|launch_runtime\s*=\s*LAUNCH_RUNTIME_LEGACY")
        legacy_callback = re.compile(
            r"origin\s*=\s*(?:[\"']legacy_voice_experience_callback|LEGACY_VOICE_EXPERIENCE_CALLBACK_ORIGIN)"
        )
        for path in _files(APP):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(APP))):
                self.assertIsNone(legacy_launch.search(source), "new launch_runtime=legacy_provider writer")
                self.assertIsNone(legacy_callback.search(source), "new legacy_voice_experience_callback writer")

    def test_historical_settlement_is_a_ledger_only_component_not_a_runtime(self) -> None:
        path = MODULE / "application" / "historical_settlement.py"
        source = path.read_text(encoding="utf-8")
        for symbol in (
            "VoiceSession", "TelephonyFacade", "place_outbound_call", "CreateVoiceCallCommand", "VoiceClient",
            "LiveKit", "httpx", "SipRoute", "dispatch", "dial", ".create(", "retry", "runtime_factory",
            "launch_runtime =", "voice_session_id =", "status =",
        ):
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)
        for imported in _imports(path):
            with self.subTest(imported=imported):
                self.assertFalse(imported.startswith(("app.services", "app.modules.voice.", "app.modules.telephony")))
        self.assertNotIn("legacy_runtime", path.name)
        for imported in _imports(path):  # no HTTP, no Telephony, no Voice internals, no services
            self.assertFalse(imported.startswith(("httpx", "requests", "app.api", "fastapi")), imported)
        for ownership_rule in ("call.provider", "runtime.provider", "provider_call_id"):
            self.assertIn(ownership_rule, source)  # the component, not the endpoint, owns the rules

    def test_historical_markers_stay_allowed_by_the_database(self) -> None:
        from app.modules.crm.infrastructure.models import CrmVoiceCall
        from app.modules.voice_experiences.infrastructure.submission_models import TenantVoiceRuntimeCall

        checks = {
            constraint.name: str(constraint.sqltext)
            for table in (CrmVoiceCall.__table__, TenantVoiceRuntimeCall.__table__)
            for constraint in table.constraints
            if getattr(constraint, "sqltext", None) is not None
        }
        self.assertIn("legacy_voice_experience_callback", checks["ck_crm_voice_calls_origin"])
        self.assertIn("legacy_provider", checks["ck_voice_runtime_launch_runtime"])

    def test_webrtc_join_info_is_a_frozen_framework_free_dto(self) -> None:
        import typing

        from app.modules.voice import public as voice_public

        dto = voice_public.WebRTCJoinInfo
        self.assertTrue(is_dataclass(dto) and dto.__dataclass_params__.frozen)
        self.assertTrue(hasattr(dto, "__slots__"))
        hints = typing.get_type_hints(dto)
        self.assertEqual(set(hints), {"voice_session_id", "server_url", "room_name", "participant_token", "expires_in"})
        self.assertFalse(any(_hides_implementation(hint) for hint in hints.values()))

    def test_the_public_response_schema_cannot_leak_internal_identifiers(self) -> None:
        from app.modules.voice_experiences.api.schemas.public_voice_calls import PublicVoiceCallResponse

        self.assertEqual(
            set(PublicVoiceCallResponse.model_fields),
            {"status", "server_url", "participant_token", "expires_in", "capabilities"},
        )

    def test_canonical_callback_application_has_no_provider_sip_or_legacy_imports(self) -> None:
        forbidden = (
            "ultravox", "app.services", "app.models", "app.modules.voice_legacy", "app.modules.voice_providers",
            "app.modules.voice.application", "app.modules.voice.infrastructure",
            "app.modules.telephony.application", "app.modules.telephony.infrastructure",
            "app.modules.crm.infrastructure", "app.modules.agents.infrastructure",
            "app.modules.voice_experiences.infrastructure.legacy_runtime",
        )
        for name in ("public_callback_service.py", "callback_worker.py", "callback_ledger.py", "launch_context.py"):
            path = MODULE / "application" / name
            source = path.read_text(encoding="utf-8")
            for imported in _imports(path):
                with self.subTest(path=name, imported=imported):
                    self.assertFalse(
                        any(imported == prefix or imported.startswith(prefix + ".") for prefix in forbidden), imported
                    )
            for symbol in (
                "VoiceClient", "VoiceConfigService", "VoiceLegacyFacade", "TenantVoiceAgentConfig",
                "TenantVoiceProviderConfig", "LiveKitSipService", "VoiceRuntimeDispatcher", "LiveKitRuntimeBackend",
                "VoiceSipRouteConfig", "start_outbound_call",
            ):
                self.assertNotIn(symbol, source, f"{symbol} in {name}")

    def test_voice_experiences_never_reaches_the_sip_transport_or_the_runtime_backend(self) -> None:
        for path in _files(MODULE):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(APP))):
                for symbol in ("LiveKitSipService", "VoiceRuntimeDispatcher", "LiveKitRuntimeBackend"):
                    self.assertNotIn(symbol, source)

    def test_livekit_sip_transport_is_only_reachable_from_telephony(self) -> None:
        for path in _files(APP):
            relative = path.relative_to(APP)
            if relative.parts[:2] == ("modules", "telephony"):
                continue
            for imported in _imports(path):
                with self.subTest(path=str(relative), imported=imported):
                    self.assertNotEqual(imported, "app.modules.telephony.infrastructure.livekit_sip")

    def test_the_callback_worker_port_is_async(self) -> None:
        from app.modules.voice_experiences import public

        self.assertTrue(inspect.iscoroutinefunction(public.VoiceCallbackWorkerPort.process_once))

    def test_openapi_is_unchanged_from_the_base(self) -> None:
        """PR #136 keeps every public contract: the full OpenAPI (paths, request bodies, responses,
        errors, component schemas) equals the base branch's, generated in this same environment."""
        from app.main import app

        base, branch = _base_snapshot()["openapi"], json.loads(json.dumps(app.openapi()))
        self.assertEqual(branch["paths"], base["paths"])
        self.assertEqual(branch["components"], base["components"])
        self.assertEqual(
            {key: value for key, value in branch.items() if key not in ("paths", "components")},
            {key: value for key, value in base.items() if key not in ("paths", "components")},
        )
        callback = branch["paths"]["/api/v1/public/voice-experiences/{slug}/callback-requests"]["post"]
        self.assertEqual(set(callback["responses"]) & {"202"}, {"202"})

    def test_openapi_digest_detects_schema_level_changes(self) -> None:
        import copy

        spec = {
            "paths": {
                "/x": {
                    "post": {
                        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/A"}}}},
                        "responses": {"200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/A"}}}}},
                    }
                }
            },
            "components": {
                "schemas": {
                    "A": {
                        "type": "object",
                        "required": ["agent_config_id"],
                        "properties": {"agent_config_id": {"type": "string"}},
                    }
                }
            },
        }
        baseline = _openapi_digest(spec)
        self.assertEqual(baseline, _openapi_digest(copy.deepcopy(spec)))
        mutations = {
            "nullable": lambda d: d["components"]["schemas"]["A"]["properties"]["agent_config_id"].update(
                anyOf=[{"type": "string"}, {"type": "null"}]
            ),
            "required": lambda d: d["components"]["schemas"]["A"].update(required=[]),
            "requestBody": lambda d: d["paths"]["/x"]["post"]["requestBody"]["content"]["application/json"].update(
                schema={"$ref": "#/components/schemas/B"}
            ),
            "response": lambda d: d["paths"]["/x"]["post"]["responses"]["200"]["content"]["application/json"].update(
                schema={"type": "string"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(change=name):
                changed = copy.deepcopy(spec)
                mutate(changed)
                self.assertNotEqual(baseline, _openapi_digest(changed))


if __name__ == "__main__":
    unittest.main()
