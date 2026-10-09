from __future__ import annotations

import ast
import hashlib
import inspect
import io
import json
import os
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
_OPENAPI_SCRIPT = (
    "import hashlib, json, sys; sys.path.insert(0, '.'); from app.main import app; "
    "print(hashlib.sha256(json.dumps(app.openapi(), sort_keys=True, separators=(',', ':')).encode()).hexdigest())"
)


def _openapi_digest(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _base_openapi_digest() -> str:
    """Digest of the base ref's full OpenAPI, produced by importing its ``app`` from ``git archive``."""
    repo = Path(__file__).resolve().parent.parent
    archive = subprocess.run(
        ["git", "archive", BASE_REF, "backend/app"], cwd=repo, capture_output=True
    )
    if archive.returncode != 0:
        if os.environ.get("CI"):
            raise AssertionError(f"base ref {BASE_REF} unavailable in CI: {archive.stderr.decode()[:200]}")
        raise unittest.SkipTest(f"base ref {BASE_REF} not available locally")
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(tmp, filter="data")
        env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        result = subprocess.run(
            [sys.executable, "-c", _OPENAPI_SCRIPT],
            cwd=Path(tmp) / "backend",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(f"base OpenAPI generation failed: {result.stderr[-500:]}")
    return result.stdout.strip().splitlines()[-1]


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
        self.assertGreaterEqual(len(dtos), 4)
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
        self.assertGreaterEqual(len(callables), 8)
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
            typing.get_type_hints(public.create_runtime_webhook_service)["return"],
            public.VoiceRuntimeWebhookServicePort,
        )
        self.assertIs(
            typing.get_type_hints(public.create_callback_worker)["return"],
            public.VoiceCallbackWorkerPort,
        )
        self.assertIs(
            typing.get_type_hints(public.create_context_schema_reader)["return"],
            public.VoiceContextSchemaReader,
        )

    def test_runtime_webhook_target_is_a_framework_free_handle(self) -> None:
        import typing

        from app.modules.voice_experiences.public import VoiceRuntimeWebhookTarget

        self.assertTrue(VoiceRuntimeWebhookTarget.__dataclass_params__.frozen)
        for name, annotation in typing.get_type_hints(VoiceRuntimeWebhookTarget).items():
            with self.subTest(field=name):
                self.assertIn(annotation, (str, str | None))

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

    def test_legacy_adapters_do_not_touch_identity_orm(self) -> None:
        for path in _files(MODULE / "infrastructure" / "legacy_runtime"):
            for imported in _imports(path):
                with self.subTest(path=path.name, imported=imported):
                    self.assertNotEqual(imported, "app.models")
                    self.assertFalse(imported.startswith("app.modules.identity.infrastructure"))

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

    def test_ddl_matches_develop_baseline(self) -> None:
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
        actual = hashlib.sha256("\n".join(ddl).encode()).hexdigest()
        self.assertEqual(actual, "ed1d743672039c752c16ee4c070b69e3cc2ddfadc6c6405c46eb2a69d227f071")

    def test_openapi_matches_develop_baseline(self) -> None:
        """Full OpenAPI (paths, requestBody, responses, components.schemas, enums, required,
        nullable, defaults, constraints, $refs) must equal the base branch's, generated in
        this same environment so dependency versions cannot create false diffs."""
        from app.main import app

        base = _base_openapi_digest()
        self.assertEqual(
            _openapi_digest(app.openapi()),
            base,
            "OpenAPI differs from the base branch; no normalization is applied.",
        )

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
