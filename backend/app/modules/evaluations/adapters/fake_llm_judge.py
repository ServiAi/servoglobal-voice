"""Test/development LlmJudgePort adapter. It is NOT a heuristic judge: it returns exactly the
structured responses (or errors) it was configured with and records what it received."""

from __future__ import annotations

from app.modules.evaluations.domain.errors import SemanticJudgeConfigurationError
from app.modules.evaluations.domain.semantic_judge import (
    JudgeMetadata,
    SemanticJudgeRequest,
    SemanticJudgeResponse,
)

FAKE_PROVIDER = "fake"
FAKE_MODEL = "fake-semantic-judge-v1"
FAKE_METADATA = JudgeMetadata(provider=FAKE_PROVIDER, requested_model=FAKE_MODEL, resolved_model=FAKE_MODEL)


class FakeLlmJudge:
    def __init__(self, responses: dict[str, SemanticJudgeResponse | Exception | object] | None = None) -> None:
        """``responses`` maps criterion_key to a response, an exception to raise, or any other
        object (returned as-is to simulate malformed adapter output)."""
        self.responses = dict(responses or {})
        self.requests: list[SemanticJudgeRequest] = []

    def evaluate(self, request: SemanticJudgeRequest) -> SemanticJudgeResponse:
        self.requests.append(request)
        configured = self.responses.get(request.criterion_key)
        if configured is None:
            raise SemanticJudgeConfigurationError("semantic_fake_judge_not_configured")
        if isinstance(configured, Exception):
            raise configured
        return configured


def fake_response(
    criterion_key: str, verdict: str, score: int | None, *, reason: str = "Fixture reason.",
    evidence_turn_ids: tuple[str, ...] = (),
) -> SemanticJudgeResponse:
    return SemanticJudgeResponse(criterion_key, verdict, score, reason, evidence_turn_ids, FAKE_METADATA)
