from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.domain.tool_registry import get_tool
from app.services.integration_event_service import IntegrationEventService
from app.services.voice_session_service import VoiceSessionError, VoiceSessionService


class ToolDispatchError(ValueError):
    pass


class ToolNotFoundError(ToolDispatchError):
    pass


class ToolNotAvailableError(ToolDispatchError):
    pass


class ToolArgumentError(ToolDispatchError):
    pass


class ToolExecutionError(ToolDispatchError):
    pass


def _handle_check_availability(db: Session, tenant_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.booking_service import BookingService

    try:
        return BookingService(db).get_available_slots_for_tenant(
            tenant_id=tenant_id, date_input=str(arguments.get("date") or "")
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc


def _handle_send_whatsapp(db: Session, tenant_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from app.services.whatsapp_message_service import WhatsAppMessageService

    variables = {str(k): str(v) for k, v in (arguments.get("variables") or {}).items()}
    try:
        result = WhatsAppMessageService(db).send_template_notification(
            tenant_id=tenant_id,
            to_phone=str(arguments.get("to_phone") or ""),
            template_key=str(arguments.get("template_key") or ""),
            variables=variables,
            metadata={"source": "agent_tool"},
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"status": result.status, "provider_message_id": result.provider_message_id}


# Allowlist only. A tool key is resolved to a handler exclusively through
# this literal mapping -- never via dynamic import, getattr(), or any
# string the model/runtime supplies. A key that isn't a literal key in this
# dict can never execute, no matter what the Tool Registry or an agent's
# binding says.
_HANDLERS: dict[str, Callable[[Session, str, dict[str, Any]], dict[str, Any]]] = {
    "calendar.check_availability": _handle_check_availability,
    "whatsapp.send_message": _handle_send_whatsapp,
}


class ToolDispatchService:
    """Executes one tool call for a live VoiceSession. Re-resolves and
    re-validates everything from the database rather than trusting the
    compiled RuntimeSessionSpecV1 the runtime already has -- the runtime
    process is a separate, less-trusted deploy, so the tool boundary lives
    here, not there."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def invoke(self, session_id: str, tool_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        session = VoiceSessionService(self.db).get(session_id)
        if session.status in {"ended", "failed", "cancelled"} or session.agent_id is None or session.agent.status == "archived":
            raise VoiceSessionError("Voice session is terminal.")
        version = session.agent_version
        bindings = (version.runtime_binding_json or {}).get("tools", []) if version else []
        binding = next(
            (b for b in bindings if isinstance(b, dict) and b.get("key") == tool_key),
            None,
        )
        if binding is None or not binding.get("enabled", True):
            raise ToolNotFoundError(tool_key)
        tool = get_tool(tool_key)
        if tool is None or tool.status != "available":
            raise ToolNotAvailableError(tool_key)
        handler = _HANDLERS.get(tool_key)
        if handler is None:
            raise ToolNotAvailableError(tool_key)
        self._validate_arguments(tool.input_schema, arguments)
        try:
            result = handler(self.db, session.tenant_id, arguments)
        except ToolExecutionError:
            self._record_event(session.tenant_id, session.agent_id, tool_key, status="error")
            raise
        self._record_event(session.tenant_id, session.agent_id, tool_key, status="success")
        return result

    @staticmethod
    def _validate_arguments(input_schema: dict[str, Any], arguments: dict[str, Any]) -> None:
        """Minimal, purpose-built shape check against the tool's declared
        input_schema (string/object properties, required list) -- not a
        general JSON Schema validator; today's two tools only need this
        much, and this stays small enough to read at a glance."""
        if not isinstance(arguments, dict):
            raise ToolArgumentError("Arguments must be an object.")
        properties = input_schema.get("properties", {})
        for required_key in input_schema.get("required", []):
            if required_key not in arguments:
                raise ToolArgumentError(f"Missing required argument '{required_key}'.")
        for key, value in arguments.items():
            spec = properties.get(key)
            if spec is None:
                raise ToolArgumentError(f"Unknown argument '{key}'.")
            expected = spec.get("type")
            if expected == "string" and not isinstance(value, str):
                raise ToolArgumentError(f"Argument '{key}' must be a string.")
            if expected == "object" and not isinstance(value, dict):
                raise ToolArgumentError(f"Argument '{key}' must be an object.")

    def _record_event(self, tenant_id: str, agent_id: str | None, tool_key: str, *, status: str) -> None:
        # Deliberately logs only the tool key and outcome, never the call
        # arguments (phone numbers, dates) or the result payload -- same
        # "no PII in audit metadata" discipline as AgentService._record_event.
        IntegrationEventService(self.db).record_event(
            tenant_id=tenant_id,
            provider="agent_builder",
            event_type="agent_tool_invoked",
            status=status,
            resource_type="agent",
            resource_id=agent_id or "",
            metadata={"tool_key": tool_key},
        )
