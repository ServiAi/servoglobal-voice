from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.modules.tools.application.contracts import (
    PlatformToolContractError,
    PlatformToolContractService,
)
from app.modules.tools.application.ports import ToolPorts
from app.modules.tools.application.resolver import ToolResolverService
from app.modules.tools.domain.errors import (  # noqa: F401 -- re-exported, historical import path
    ToolArgumentError,
    ToolDispatchError,
    ToolExecutionError,
    ToolNotAvailableError,
    ToolNotFoundError,
    validate_tool_arguments,
)
from app.modules.tools.domain.invocation import PlatformToolInvocation
from app.modules.tools.domain.registry import get_tool
from app.modules.tools.domain.resolved_tool import from_platform
from app.modules.tools.infrastructure.http_executor import CustomHttpToolExecutor
from app.modules.voice.public import (
    SessionContextEnrichmentError,
    ToolBindingView,
    ToolSessionView,
    VoiceSessionError,
)
from app.services.integration_event_service import IntegrationEventService

# Handlers reach other modules only through ToolPorts (scheduling, CRM,
# messaging, voice sessions) -- never by importing their services, and they
# only ever see DTOs (ToolSessionView, ContactRef/LeadRef), never ORM rows.
Handler = Callable[[Session, ToolPorts, str, PlatformToolInvocation, ToolSessionView], dict[str, Any]]


def _handle_check_availability(
    db: Session, ports: ToolPorts, tenant_id: str, invocation: PlatformToolInvocation, session: ToolSessionView
) -> dict[str, Any]:
    try:
        return ports.scheduling.get_available_slots(
            tenant_id=tenant_id, date_input=str(invocation.llm_args.get("date") or "")
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc


def _handle_send_whatsapp(
    db: Session, ports: ToolPorts, tenant_id: str, invocation: PlatformToolInvocation, session: ToolSessionView
) -> dict[str, Any]:
    # V2 contract: to_phone/template_key/variables are never LLM arguments
    # anymore -- PlatformToolContractService.resolve_whatsapp_send resolves
    # all three from invocation.config (admin-set template + recipient
    # strategy + variable mapping) and invocation.context (trusted session
    # identity), only ever pulling from invocation.llm_args for variables
    # explicitly mapped source=llm. See contracts.py.
    plan = PlatformToolContractService(db).resolve_whatsapp_send(tenant_id, invocation)
    try:
        result = ports.messaging.send_template(
            tenant_id=tenant_id,
            to_phone=plan.to_phone,
            template_key=plan.template_key,
            variables=plan.variables,
            metadata={"source": "agent_tool"},
            lead_id=plan.lead_id,
            contact_id=plan.contact_id,
        )
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"status": result.status, "provider_message_id": result.provider_message_id}


def _handle_create_booking(
    db: Session, ports: ToolPorts, tenant_id: str, invocation: PlatformToolInvocation, session: ToolSessionView
) -> dict[str, Any]:
    # lead_id, attendee_name and attendee_email come from the session's
    # own resolved context -- never from the LLM. See SessionContextV1 /
    # ContactResolutionService: they are trusted, tenant-scoped identity,
    # not the LLM's business intent (the "date/time to book" is).
    context = invocation.context
    if context.lead is None:
        raise ToolExecutionError("lead_context_required")
    contact = context.contact
    try:
        booking = ports.scheduling.create_lead_booking(
            tenant_id=tenant_id,
            lead_id=context.lead.id,
            start=str(invocation.llm_args.get("start") or ""),
            attendee_name=(contact.name if contact and contact.name else "Cliente"),
            attendee_email=(contact.email if contact and contact.email else ""),
            attendee_phone=contact.phone if contact else None,
            notes=invocation.llm_args.get("notes"),
        )
    # ValidationError subclasses ValueError: a malformed booking request is
    # an argument error, anything else the scheduler raises is execution.
    except ValidationError as exc:
        raise ToolArgumentError(str(exc)) from exc
    except ValueError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"booking_id": booking.id, "status": booking.status, "start_at": booking.start_at.isoformat()}


def _handle_create_lead(
    db: Session, ports: ToolPorts, tenant_id: str, invocation: PlatformToolInvocation, session: ToolSessionView
) -> dict[str, Any]:
    # phone comes from the session's own caller identity, never an
    # LLM-supplied argument -- a hallucinated/mistranscribed phone number
    # must never become the key a lead gets created or matched under.
    context = invocation.context
    caller_phone = context.caller.phone if context.caller else None
    if not caller_phone:
        raise ToolExecutionError("caller_phone_required")
    name = str(invocation.llm_args.get("name") or "")
    email = invocation.llm_args.get("email")
    contact, lead = ports.crm.get_or_create_open_lead(tenant_id=tenant_id, phone=caller_phone, email=email, name=name)
    # Fase F.1: make the newly resolved identity available to a later tool
    # call in the same session (e.g. calendar.create_booking) without the
    # LLM ever supplying lead_id/contact_id -- see
    # VoiceSessionService.enrich_context for the monotonic-only guarantee.
    try:
        ports.sessions.enrich_context(session.id, contact=contact, lead=lead, event_source="crm.create_lead")
    except SessionContextEnrichmentError as exc:
        raise ToolExecutionError(str(exc)) from exc
    return {"lead_id": lead.id, "contact_id": contact.id, "status": lead.status}


# Allowlist only. A tool key is resolved to a handler exclusively through
# this literal mapping -- never via dynamic import, getattr(), or any
# string the model/runtime supplies. A key that isn't a literal key in this
# dict can never execute, no matter what the Tool Registry or an agent's
# binding says.
_HANDLERS: dict[str, Handler] = {
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

    def __init__(self, db: Session, ports: ToolPorts | None = None) -> None:
        self.db = db
        if ports is None:
            from app.modules.tools.wiring import default_tool_ports

            ports = default_tool_ports(db)
        self.ports = ports

    def invoke(self, session_id: str, tool_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
        session = self.ports.sessions.get_tool_session(session_id)
        if session.is_terminal:
            raise VoiceSessionError("Voice session is terminal.")
        binding = session.binding(tool_key)
        if binding is None or not binding.enabled:
            raise ToolNotFoundError(tool_key)

        # custom.* tools are dispatched through a dedicated executor
        # resolved from the DB-backed tenant catalog, never through
        # _HANDLERS -- everything below this guard is the original,
        # untouched Platform Tool path.
        if tool_key.startswith("custom."):
            return self._invoke_custom(session, tool_key, binding, arguments)

        tool = get_tool(tool_key)
        if tool is None or tool.status != "available":
            raise ToolNotAvailableError(tool_key)
        handler = _HANDLERS.get(tool_key)
        if handler is None:
            raise ToolNotAvailableError(tool_key)

        resolved = from_platform(tool)
        binding_config = dict(binding.config)
        contract = PlatformToolContractService(self.db)
        # Argument-shape validation stays outside the timed/recorded block,
        # same as before this refactor: a malformed LLM call is never
        # counted as a tool execution failure.
        try:
            contract.validate_llm_arguments(resolved, binding_config, arguments)
        except PlatformToolContractError as exc:
            raise ToolArgumentError(exc.message) from exc

        context = session.context
        started = perf_counter()
        try:
            # Each handler still validates its own context requirements
            # itself (lead_context_required, caller_phone_required,
            # whatsapp_recipient_context_required/whatsapp_legacy_binding_
            # unsupported via PlatformToolContractService.resolve_whatsapp_send)
            # and raises its own stable code -- PlatformToolContractService.
            # validate_context is not called generically here so it can
            # never pre-empt a handler's own, already-tested error code with
            # a more generic one. context_requirements stays declarative
            # metadata for the catalog API / Agent Builder UI (see
            # ToolCatalogService), not a second enforcement layer.
            invocation = contract.build_invocation(llm_args=arguments, context=context, config=binding_config)
            result = handler(self.db, self.ports, session.tenant_id, invocation, session)
        except PlatformToolContractError as exc:
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            self._record_event(session.tenant_id, session.agent_id, tool_key, status="error")
            self._record_context_tool_event(
                session,
                tool_key,
                status="error",
                duration_ms=duration_ms,
                error_code=self._safe_error_code(exc.code),
            )
            raise ToolExecutionError(str(exc)) from exc
        except ToolExecutionError as exc:
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            self._record_event(session.tenant_id, session.agent_id, tool_key, status="error")
            self._record_context_tool_event(
                session,
                tool_key,
                status="error",
                duration_ms=duration_ms,
                error_code=self._safe_error_code(str(exc)),
            )
            raise
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        self._record_event(session.tenant_id, session.agent_id, tool_key, status="success")
        self._record_context_tool_event(
            session,
            tool_key,
            status="success",
            duration_ms=duration_ms,
            summary=self._result_summary(tool_key, result),
        )
        return result

    def _invoke_custom(
        self, session: ToolSessionView, tool_key: str, binding: ToolBindingView, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        row = ToolResolverService(self.db).get_active_custom_tool(session.tenant_id, tool_key)
        if row is None:
            raise ToolNotAvailableError(tool_key)
        tenant_tool, config = row
        context = session.context
        started = perf_counter()
        try:
            result = CustomHttpToolExecutor(self.db).execute(
                tenant_id=session.tenant_id,
                tenant_tool=tenant_tool,
                config=config,
                arguments=arguments,
                context=context,
                binding_config=dict(binding.config),
            )
        except ToolExecutionError as exc:
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            self._record_event(session.tenant_id, session.agent_id, tool_key, status="error")
            self._record_context_tool_event(
                session,
                tool_key,
                status="error",
                duration_ms=duration_ms,
                error_code=self._safe_error_code(str(exc)),
            )
            raise
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        self._record_event(session.tenant_id, session.agent_id, tool_key, status="success")
        self._record_context_tool_event(
            session,
            tool_key,
            status="success",
            duration_ms=duration_ms,
            summary="completed",
        )
        return result

    def _record_context_tool_event(
        self,
        session: ToolSessionView,
        tool_key: str,
        *,
        status: str,
        duration_ms: int,
        summary: str | None = None,
        error_code: str | None = None,
    ) -> None:
        # Per-session narrative event (alongside the tenant-wide
        # agent_tool_invoked audit event above) -- lets "what happened in
        # this call" be read from VoiceSession.events alone. Same no-PII
        # discipline: tool_key + outcome only, never arguments/results.
        self.ports.sessions.record_event(
            session.id, "session.context.tool_used", source="control-plane",
            payload={
                "tool_key": tool_key,
                "status": status,
                "duration_ms": duration_ms,
                **({"summary": summary} if summary else {}),
                **({"error_code": error_code} if error_code else {}),
            },
        )

    @staticmethod
    def _safe_error_code(value: str) -> str:
        return value if 0 < len(value) <= 80 and value.replace("_", "").isalnum() else "tool_execution_failed"

    @staticmethod
    def _result_summary(tool_key: str, result: dict[str, Any]) -> str:
        if tool_key == "calendar.check_availability":
            slots = result.get("slots")
            return f"{len(slots) if isinstance(slots, list) else 0} horarios"
        if tool_key == "calendar.create_booking":
            return "booking_created"
        if tool_key in {"whatsapp.send_message", "crm.create_lead"}:
            status = result.get("status")
            return str(status)[:40] if isinstance(status, str) else "completed"
        return "completed"

    # Kept for existing callers/tests; the one implementation lives in
    # app.modules.tools.domain.errors.
    _validate_arguments = staticmethod(validate_tool_arguments)

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
