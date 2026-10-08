from dataclasses import dataclass
from datetime import datetime

from app.modules.evaluations.domain.errors import EvaluationInvalidEvidence


@dataclass(frozen=True)
class ToolOutcomeEvidence:
    tool_key: str
    status: str
    duration_ms: int
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_key or len(self.tool_key) > 100:
            raise EvaluationInvalidEvidence("evaluation_tool_key_invalid")
        if self.status not in {"success", "error"} or self.duration_ms < 0:
            raise EvaluationInvalidEvidence("evaluation_tool_outcome_invalid")
        if self.error_code is not None and (
            len(self.error_code) > 80 or not self.error_code.replace("_", "").isalnum()
        ):
            raise EvaluationInvalidEvidence("evaluation_tool_error_code_invalid")


@dataclass(frozen=True)
class VoiceSessionEvidence:
    tenant_id: str
    session_id: str
    purpose: str
    status: str
    agent_version_id: str | None
    ended_at: datetime
    error_code: str | None
    tool_outcomes: tuple[ToolOutcomeEvidence, ...]

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.session_id:
            raise EvaluationInvalidEvidence("evaluation_subject_required")
        if self.purpose not in {"qa", "production"}:
            raise EvaluationInvalidEvidence("evaluation_session_purpose_invalid")
        if self.status not in {"ended", "failed", "cancelled"}:
            raise EvaluationInvalidEvidence("evaluation_session_not_terminal")
        if self.ended_at.tzinfo is None or self.ended_at.utcoffset() is None:
            raise EvaluationInvalidEvidence("evaluation_terminal_time_must_be_aware")
        if self.error_code is not None and (
            len(self.error_code) > 80 or not self.error_code.replace("_", "").isalnum()
        ):
            raise EvaluationInvalidEvidence("evaluation_error_code_invalid")

    @property
    def tool_success_count(self) -> int:
        return sum(outcome.status == "success" for outcome in self.tool_outcomes)

    @property
    def tool_failure_count(self) -> int:
        return sum(outcome.status == "error" for outcome in self.tool_outcomes)


