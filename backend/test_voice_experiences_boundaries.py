from __future__ import annotations

import ast
import hashlib
import inspect
import subprocess
import sys
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
        from app.modules.voice_experiences import public

        for name in ("VoiceContextFieldSnapshot", "VoiceContextSchemaSnapshot"):
            dto = getattr(public, name)
            self.assertTrue(is_dataclass(dto))
            self.assertTrue(dto.__dataclass_params__.frozen)
            for field in fields(dto):
                self.assertNotIn("Any", str(field.type))
                self.assertNotIn("sqlalchemy", str(field.type).lower())
        for name, value in vars(public).items():
            if inspect.isfunction(value) and value.__module__ == public.__name__:
                signature = str(inspect.signature(value)).lower()
                self.assertNotIn("sqlalchemy", signature)
                self.assertNotIn("fastapi", signature)
                self.assertNotIn("any", signature)

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
        from app.main import app

        # Hash only the route contract (method, path, operationId, response codes,
        # parameters): the full schema dump also shifts with pydantic/fastapi versions.
        spec = app.openapi()
        ops = sorted(
            f"{method.upper()} {path} {op.get('operationId')} {sorted(op.get('responses', {}))} "
            f"{sorted(p['name'] + p['in'] for p in op.get('parameters', []))}"
            for path, item in spec["paths"].items()
            for method, op in item.items()
        )
        actual = hashlib.sha256("\n".join(ops).encode()).hexdigest()
        self.assertEqual(actual, "f97e52fb51b373f8c48a2d720480e10ea6fb2b918d01716068875783e46ee47c")


if __name__ == "__main__":
    unittest.main()
