from __future__ import annotations

import ast
import dataclasses
import unittest
from pathlib import Path

from app.modules.agents.public import AgentEvaluationSnapshot
from app.modules.evaluations.domain.semantic_evidence import SemanticEvaluationEvidenceV1
from app.modules.voice.public import VoiceConversationEvidence, VoiceToolOutcome

APP = Path(__file__).resolve().parent / "app"


class SemanticEvidenceBoundaryTests(unittest.TestCase):
    def test_evaluations_only_imports_voice_and_agents_public_boundaries(self) -> None:
        forbidden = (
            "app.modules.voice.infrastructure",
            "app.modules.voice.application",
            "app.modules.agents.infrastructure",
            "app.modules.agents.application",
        )
        for path in (APP / "modules" / "evaluations").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = (
                    node.module
                    if isinstance(node, ast.ImportFrom)
                    else node.names[0].name
                    if isinstance(node, ast.Import)
                    else ""
                )
                self.assertFalse(module.startswith(forbidden), f"{path}: {module}")

    def test_public_evidence_contracts_are_frozen_dataclasses_without_secret_fields(self) -> None:
        for dto in (AgentEvaluationSnapshot, VoiceConversationEvidence, VoiceToolOutcome, SemanticEvaluationEvidenceV1):
            self.assertTrue(dataclasses.is_dataclass(dto))
            self.assertTrue(dto.__dataclass_params__.frozen)
            names = {field.name.lower() for field in dataclasses.fields(dto)}
            self.assertFalse(any(any(part in name for part in ("api_key", "token", "credential", "header", "secret")) for name in names))


if __name__ == "__main__":
    unittest.main()
