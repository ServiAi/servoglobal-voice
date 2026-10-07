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
            "livekit", "elevenlabs", "ultravox", "cohere", "mistralai",
        )
        for folder in (MODULE / "domain", MODULE / "application"):
            for path in folder.rglob("*.py"):
                for imported in _imports(path):
                    self.assertFalse(imported.startswith(prohibited), f"{path}: {imported}")

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
