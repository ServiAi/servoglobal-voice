from __future__ import annotations

from typing import Any, Callable

from sqlalchemy.orm import Session

from app.domain.tool_registry import get_tool
from app.models.voice_sessions import VoiceSession
from app.schemas.session_context import SessionContextV1
from app.services.integration_event_service import IntegrationEventService
from app.services.voice_session_service import (
    SessionContextEnrichmentError,
    VoiceSessionError,
    VoiceSessionService,
)


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


def _handle_check_availability(db: Session, tenant_id: str, arguments: dict[str, Any], context: SessionContextV1, session: VoiceSession) -> dict[str, Any]:
    from app.services.booking_service import BookingService

    try:
        return BookingService(db).get_available_slots_for_tenant(
            tenant_id=tenant_id, date_input=str(arguments.get("date") or "")
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc


def _handle_send_whatsapp(db: Session, tenant_id: str, arguments: dict[str, Any], context: SessionContextV1, session: VoiceSession) -> dict[str, Any]:
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


def _handle_create_booking(db: Session, tenant_id: str, arguments: dict[str, Any], context: SessionContextV1, session: VoiceSession) -> dict[str, Any]:
    # lead_id, attendee_name and attendee_email come from the session's
    # own resolved context -- never from the LLM. See SessionContextV1 /
    # ContactResolutionService: they are trusted, tenant-scoped identity,
    # not the LLM's business intent (the "date/time to book" is).
    from pydantic import ValidationError

    from app.schemas.crm import BookingCreateRequest
    from app.services.booking_service import BookingService

    if context.lead is None:
        raise ToolExecutionError("lead_context_required")
    contact = context.contact
    try:
        body = BookingCreateRequest(
            start=str(arguments.get("start") or ""),
            attendee_name=(contact.name if contact and contact.name else "Cliente"),
            attendee_email=(contact.email if contact and contact.email else ""),
            attendee_phone=contact.phone if contact else None,
            notes=arguments.get("notes"),
        )
    except ValidationError as exc:
        raise ToolArgumentError(str(exc)) from exc
    try:
        booking = BookingService(db).create_lead_booking(tenant_id=tenant_id, lead_id=context.lead.id, body=body)
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"booking_id": booking.id, "status": booking.status, "start_at": booking.start_at.isoformat()}


def _handle_create_lead(db: Session, tenant_id: str, arguments: dict[str, Any], context: SessionContextV1, session: VoiceSession) -> dict[str, Any]:
    # phone comes from the session's own caller identity, never an
    # LLM-supplied argument -- a hallucinated/mistranscribed phone number
    # must never become the key a lead gets created or matched under.
    from app.services.crm_contact_service import CrmContactService
    from app.services.crm_lead_service import CrmLeadService

    caller_phone = context.caller.phone if context.caller else None
    if not caller_phone:
        raise ToolExecutionError("caller_phone_required")
    name = str(arguments.get("name") or "")
    email = arguments.get("email")
    contact = CrmContactService(db).get_or_create_contact(tenant_id, caller_phone, email, name)
    lead = CrmLeadService(db).get_or_create_open_lead(tenant_id, contact.id)
    # Fase F.1: make the newly resolved identity available to a later tool
    # call in the same session (e.g. calendar.create_booking) without the
    # LLM ever supplying lead_id/contact_id -- see
    # VoiceSessionService.enrich_context for the monotonic-only guarantee.
    try:
        VoiceSessionService(db).enrich_context(session, contact=contact, lead=lead, event_source="crm.create_lead")
    except SessionContextEnrichmentError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"lead_id": lead.id, "contact_id": contact.id, "status": lead.status}


# Allowlist only. A tool key is resolved to a handler exclusively through
# this literal mapping -- never via dynamic import, getattr(), or any
# string the model/runtime supplies. A key that isn't a literal key in this
# dict can never execute, no matter what the Tool Registry or an agent's
# binding says.
_HANDLERS: dict[str, Callable[[Session, str, dict[str, Any], SessionContextV1, VoiceSession], dict[str, Any]]] = {
    "calendar.check_availability": _handle_check_availability,
    "whatsapp.send_message": _handle_send_whatsapp,
    "calendar.create_booking": _handle_create_booking,
    "crm.create_lead": _handle_create_lead,
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
        context = SessionContextV1.model_validate(session.session_context_json or {})
        try:
            result = handler(self.db, session.tenant_id, arguments, context, session)
        except ToolExecutionError:
            self._record_event(session.tenant_id, session.agent_id, tool_key, status="error")
            self._record_context_tool_event(session, tool_key, status="error")
            raise
        self._record_event(session.tenant_id, session.agent_id, tool_key, status="success")
        self._record_context_tool_event(session, tool_key, status="success")
        return result

    def _record_context_tool_event(self, session: VoiceSession, tool_key: str, *, status: str) -> None:
        # Per-session narrative event (alongside the tenant-wide
        # agent_tool_invoked audit event above) -- lets "what happened in
        # this call" be read from VoiceSession.events alone. Same no-PII
        # discipline: tool_key + outcome only, never arguments/results.
        VoiceSessionService(self.db).record_event(
            session, "session.context.tool_used", source="control-plane",
            payload={"tool_key": tool_key, "status": status},
        )

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
