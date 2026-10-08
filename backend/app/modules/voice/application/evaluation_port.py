from typing import Protocol


class EvaluationRequestPort(Protocol):
    def request_terminal_session(
        self,
        *,
        tenant_id: str,
        session_id: str,
        purpose: str,
        status: str,
        agent_version_id: str | None,
        ended_at,
        error_code: str | None,
        tool_outcomes: tuple[dict, ...],
    ) -> None: ...
