from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path

APP = Path(__file__).parent / "app"
MODULE = APP / "modules" / "evaluations"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    modules.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    return modules


class EvaluationsBoundaryTests(unittest.TestCase):
    def test_application_and_domain_do_not_import_orm_or_provider_sdks(self) -> None:
        prohibited = (
            "sqlalchemy", "openai", "anthropic", "google.genai", "google.generativeai",
            "livekit", "elevenlabs", "ultravox", "cohere", "mistralai", "openrouter", "google",
            "httpx", "requests", "urllib", "aiohttp", "socket",
        )
        for folder in (MODULE / "domain", MODULE / "application", MODULE / "adapters"):
            for path in folder.rglob("*.py"):
                for imported in _imports(path):
                    self.assertFalse(imported.startswith(prohibited), f"{path}: {imported}")

    def test_semantic_engine_only_reaches_voice_and_agents_through_public(self) -> None:
        for path in MODULE.rglob("*.py"):
            for imported in _imports(path):
                for other in ("voice", "agents"):
                    if imported.startswith(f"app.modules.{other}"):
                        self.assertEqual(imported, f"app.modules.{other}.public", f"{path}: {imported}")

    def test_judge_contract_carries_no_orm_credentials_or_http_objects(self) -> None:
        import dataclasses
        import typing

        from app.modules.evaluations.domain.semantic_judge import (
            JudgeMetadata,
            SemanticJudgeRequest,
            SemanticJudgeResponse,
        )

        forbidden = ("api_key", "apikey", "secret", "authorization", "credential", "header", "password",
                     "raw_body", "session", "db", "connection", "engine", "client", "http", "url")
        for contract in (SemanticJudgeRequest, SemanticJudgeResponse, JudgeMetadata):
            hints = typing.get_type_hints(contract)
            for field in dataclasses.fields(contract):
                self.assertFalse(any(word in field.name.lower() for word in forbidden), field.name)
                self.assertNotIn("sqlalchemy", repr(hints[field.name]).lower(), field.name)
            self.assertTrue(contract.__dataclass_params__.frozen)

    def test_provenance_is_a_closed_secret_free_whitelist(self) -> None:
        from _semantic_engine_fixtures import good_judge, make_evidence
        from app.modules.evaluations.application.semantic_evaluator import (
            SemanticEvaluator,
        )
        from app.modules.evaluations.domain.semantic_definition import (
            semantic_quality_criteria,
        )

        result = SemanticEvaluator(good_judge()).evaluate(semantic_quality_criteria(), make_evidence())
        allowed = {"provider", "requested_model", "resolved_model", "model_revision", "prompt_key",
                   "prompt_version", "prompt_hash", "rubric_version", "schema_version",
                   "implementation_version", "latency_ms", "input_tokens", "output_tokens"}
        for criterion in result.criteria:
            self.assertEqual(set(criterion.provenance), allowed)

    def test_fake_judge_is_not_wired_into_runtime_code(self) -> None:
        for path in APP.rglob("*.py"):
            if path.is_relative_to(MODULE / "adapters"):
                continue
            for imported in _imports(path):
                self.assertNotIn("fake_llm_judge", imported, f"{path}: {imported}")

    def test_other_modules_only_import_evaluations_public(self) -> None:
        for path in APP.rglob("*.py"):
            if path.is_relative_to(MODULE):
                continue
            # The global metadata registry is the existing composition exception.
            if path == APP / "models" / "__init__.py":
                continue
            for imported in _imports(path):
                if imported.startswith("app.modules.evaluations"):
                    self.assertEqual(imported, "app.modules.evaluations.public", f"{path}: {imported}")

    def test_evaluations_models_have_no_cross_module_relationships(self) -> None:
        source = (MODULE / "infrastructure" / "models.py").read_text(encoding="utf-8")
        self.assertNotIn("relationship(", source)
        for imported in _imports(MODULE / "infrastructure" / "models.py"):
            self.assertFalse(imported.startswith((
                "app.modules.voice", "app.modules.analytics", "app.modules.crm",
                "app.modules.agents", "app.modules.scheduling",
            )), imported)

    def test_public_import_does_not_load_sqlalchemy_or_provider_orms(self) -> None:
        code = (
            "import sys; import app.modules.evaluations.public; "
            "assert not any(x == 'sqlalchemy' or x.startswith('sqlalchemy.') for x in sys.modules); "
            "assert not any(x.startswith(('openai', 'anthropic', 'google.genai', 'app.modules.voice.infrastructure', "
            "'app.modules.analytics.infrastructure', 'app.modules.crm.infrastructure', 'app.modules.agents.infrastructure')) "
            "for x in sys.modules)"
        )
        subprocess.run([sys.executable, "-c", code], cwd=APP.parent, check=True)


if __name__ == "__main__":
    unittest.main()
