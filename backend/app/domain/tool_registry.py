from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ToolContextRequirement:
    """One SessionContextV1 path a platform tool's handler reads server-side
    instead of asking the LLM for it. Declarative only -- PlatformToolContractService
    is what actually enforces it against a live SessionContextV1 at dispatch
    time; this is metadata for the catalog API and the Agent Builder UI."""

    path: str
    required: bool = True
    description: str = ""


@dataclass(frozen=True)
class ToolDefinition:
    """A platform-level tool a serviglobal_managed agent can be bound to.

    `status="available"` means a real, tested execution path exists end to
    end (see ToolDispatcher / the internal tool-invoke endpoint) -- never
    add a row here as "available" ahead of that path actually working.
    `status="planned"` documents a real, evaluated candidate (the required
    service already exists) that isn't wired for execution yet -- it is
    never selectable from the Agent Builder UI or bindable on an agent; it
    exists so the catalog stays forward-compatible without a redesign when
    the missing piece (e.g. call-scoped lead/contact resolution) lands.

    `input_schema` is the LLM-facing (Function Calling) schema -- the only
    surface the model gets to decide. For a tool whose real LLM schema
    depends on how the tenant configured it (e.g. whatsapp.send_message's
    per-template variable mapping), this is the static/base shape only;
    PlatformToolContractService.compile_llm_schema computes the effective,
    binding-aware schema actually sent to the compiler and the dispatcher.
    `context_requirements` and `binding_config_schema` are empty for tools
    with no session-context or admin-configuration surface -- declared
    explicitly rather than left implicit, even when empty.
    """

    key: str
    name: str
    description: str
    status: Literal["available", "planned"]
    input_schema: dict[str, Any]
    required_integration: Literal["booking", "whatsapp", "crm", "chatwoot"] | None
    capabilities: dict[str, bool] = field(default_factory=dict)
    context_requirements: tuple[ToolContextRequirement, ...] = ()
    binding_config_schema: dict[str, Any] = field(default_factory=dict)


class ToolRegistryValidationError(ValueError):
    pass


# Admin-facing (Agent Builder) contract for whatsapp.send_message's binding
# config -- descriptive metadata surfaced through the tool catalog API for
# the configurator UI. Structural validation of an actual binding is done
# by hand in PlatformToolContractService (this codebase never adds a
# jsonschema dependency; every other schema check here -- e.g.
# ToolDispatchService._validate_arguments -- is hand-rolled too), not by
# validating against this dict directly.
_WHATSAPP_BINDING_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contract_version": {"type": "integer", "const": 2},
        "template_key": {"type": "string", "description": "TenantWhatsAppTemplate.template_key, must be status=approved for this tenant."},
        "recipient": {
            "type": "object",
            "properties": {
                "strategy": {
                    "type": "string",
                    "enum": ["contact_then_caller", "contact", "caller"],
                    "description": "contact_then_caller falls back to context.caller.phone when context.contact.phone is absent.",
                },
            },
            "required": ["strategy"],
        },
        "variables": {
            "type": "object",
            "description": "One entry per template variable key. Each entry has source=llm|context|fixed.",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["llm", "context", "fixed"]},
                    "path": {"type": "string", "description": "Required when source=context; a path from the SessionContextV1 allowlist."},
                    "value": {"description": "Required when source=fixed."},
                    "type": {"type": "string", "description": "Used when source=llm; JSON Schema type for the Function Calling property."},
                    "description": {"type": "string", "description": "Used when source=llm; shown to the model."},
                },
                "required": ["source"],
            },
        },
    },
    "required": ["contract_version", "template_key", "recipient", "variables"],
}


# Real, evaluated tool catalog. A row here is not a promise of execution --
# only `status="available"` rows have a working ToolDispatcher handler.
# Adding a tool here without a real handler is exactly the "fingir soporte
# funcional" the voice registry's own docstring warns against; the same
# rule applies here.
_TOOLS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        key="calendar.check_availability",
        name="Consultar disponibilidad",
        description="Consulta franjas horarias disponibles para agendar una cita, usando el calendario configurado del tenant (Cal.com o Google Calendar).",
        status="available",
        input_schema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Fecha solicitada (YYYY-MM-DD) o una expresión relativa como 'mañana' o 'el próximo lunes'.",
                },
            },
            "required": ["date"],
        },
        required_integration="booking",
    ),
    # V2 contract (contract_version=2 in the binding config): the LLM never
    # decides the destination or the template anymore -- see
    # PlatformToolContractService for how `input_schema` here (empty) is
    # replaced by the effective, binding-aware schema at compile/dispatch
    # time, and _WHATSAPP_BINDING_CONFIG_SCHEMA below for the admin-facing
    # contract. A published version whose binding predates V2 (`config={}`
    # or missing contract_version) is rejected at dispatch time with
    # `whatsapp_legacy_binding_unsupported` -- ToolDispatchService never
    # falls back to reading to_phone/template_key from the LLM again.
    ToolDefinition(
        key="whatsapp.send_message",
        name="Enviar WhatsApp",
        description="Envía una plantilla de WhatsApp aprobada, usando la plantilla, el destinatario y las variables configuradas por el administrador del agente.",
        status="available",
        input_schema={"type": "object", "properties": {}, "required": []},
        required_integration="whatsapp",
        context_requirements=(),
        binding_config_schema=_WHATSAPP_BINDING_CONFIG_SCHEMA,
    ),
    # Reactivated by Session Context V1: BookingService.create_lead_booking
    # needs lead_id + the lead's contact (name/email) -- both now come from
    # SessionContextV1 (ToolDispatchService loads it server-side from
    # VoiceSession.session_context_json), never from the LLM. `start` must
    # be a full ISO-8601 datetime with timezone (BookingService.parse_utc_start
    # requires it); a vague "mañana a las 10" is the LLM's job to resolve
    # into that shape before calling this tool, same as any other realtime
    # function-calling agent.
    ToolDefinition(
        key="calendar.create_booking",
        name="Crear cita",
        description="Crea una cita en el calendario del tenant para el lead identificado en esta llamada. Requiere una fecha y hora exactas en ISO-8601 con zona horaria (ej. 2026-09-15T15:00:00-05:00).",
        status="available",
        input_schema={
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Fecha y hora exactas en ISO-8601 con zona horaria, ej. 2026-09-15T15:00:00-05:00."},
                "notes": {"type": "string", "description": "Notas opcionales sobre la cita."},
            },
            "required": ["start"],
        },
        required_integration="booking",
        context_requirements=(
            ToolContextRequirement(path="lead.id", required=True, description="Lead resuelto en esta sesión."),
            ToolContextRequirement(path="contact.name", required=False, description="Nombre del asistente a la cita."),
            ToolContextRequirement(path="contact.email", required=False, description="Correo del asistente a la cita."),
            ToolContextRequirement(path="contact.phone", required=False, description="Teléfono del asistente a la cita."),
        ),
    ),
    # Reactivated by Session Context V1: CrmContactService.get_or_create_contact
    # + CrmLeadService.get_or_create_open_lead already implement exactly
    # this "find or create a Contact from a phone, then its open Lead"
    # path -- no new CRM infrastructure was built for this. `phone` is
    # deliberately NOT an LLM argument: the handler uses
    # SessionContextV1.caller.phone (session-derived), never a
    # model-supplied phone number, to avoid creating a lead under whatever
    # phone number the model happens to transcribe/hallucinate.
    ToolDefinition(
        key="crm.create_lead",
        name="Crear lead",
        description="Crea (o reutiliza) un lead en el CRM para quien llama, usando el teléfono de la llamada y el nombre/correo que indique.",
        status="available",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre de la persona."},
                "email": {"type": "string", "description": "Correo electrónico, si lo indicó."},
            },
            "required": ["name"],
        },
        required_integration="crm",
        context_requirements=(
            ToolContextRequirement(path="caller.phone", required=True, description="Teléfono del participante de la llamada."),
        ),
    ),
    # Stays planned: unrelated to Session Context V1.
    # VoiceHandoffService.trigger_handoff hard-requires a full legacy
    # TenantVoiceAgentConfig object (handoff_triggers/handoff_chatwoot_inbox_id/
    # handoff_chatwoot_team_id) -- Agent Builder's TenantAgent/TenantAgentVersion
    # has no equivalent settings surface for those. Activating this needs a
    # handoff-configuration surface on the new domain (or a signature
    # change to trigger_handoff to take plain parameters instead of the
    # ORM model), which is a separate, explicitly out-of-scope refactor.
    ToolDefinition(
        key="handoff.chatwoot",
        name="Transferir a un humano",
        description="Escala la conversación a un agente humano vía Chatwoot.",
        status="planned",
        input_schema={
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Motivo de la transferencia."},
            },
            "required": [],
        },
        required_integration="chatwoot",
    ),
)

_TOOLS_BY_KEY = {tool.key: tool for tool in _TOOLS}


def list_tools(*, status: str | None = None) -> list[ToolDefinition]:
    tools = _TOOLS
    if status is not None:
        tools = tuple(t for t in tools if t.status == status)
    return list(tools)


def get_tool(key: str) -> ToolDefinition | None:
    return _TOOLS_BY_KEY.get(key)


def validate_tool_bindings(bindings: list[Any]) -> None:
    """Pure, static validation of an agent's tool bindings: no DB, no HTTP.
    Confirms each `key` is a known, currently-executable tool and that
    there are no duplicate keys. Per-tenant integration availability (e.g.
    "is booking actually configured for this tenant") is a separate,
    tenant-aware concern checked at publish time, not here -- same split
    as voice_registry.validate_voice_compatibility vs the publish preflight.
    """
    seen: set[str] = set()
    for binding in bindings:
        key = binding.key
        if key in seen:
            raise ToolRegistryValidationError(f"Duplicate tool binding '{key}'.")
        seen.add(key)
        tool = get_tool(key)
        if tool is None:
            raise ToolRegistryValidationError(f"tool_not_found:{key}")
        if tool.status != "available":
            raise ToolRegistryValidationError(f"tool_not_available:{key}")
