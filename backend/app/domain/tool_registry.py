from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


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
    """

    key: str
    name: str
    description: str
    status: Literal["available", "planned"]
    input_schema: dict[str, Any]
    required_integration: Literal["booking", "whatsapp", "crm", "chatwoot"] | None
    capabilities: dict[str, bool] = field(default_factory=dict)


class ToolRegistryValidationError(ValueError):
    pass


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
    ToolDefinition(
        key="whatsapp.send_message",
        name="Enviar WhatsApp",
        description="Envía una plantilla de WhatsApp ya aprobada al número que indique la persona en la llamada.",
        status="available",
        input_schema={
            "type": "object",
            "properties": {
                "to_phone": {
                    "type": "string",
                    "description": "Número de teléfono en formato E.164, por ejemplo +573001234567.",
                },
                "template_key": {
                    "type": "string",
                    "description": "Clave de la plantilla de WhatsApp aprobada que se debe enviar.",
                },
                "variables": {
                    "type": "object",
                    "description": "Variables a interpolar en la plantilla.",
                },
            },
            "required": ["to_phone", "template_key"],
        },
        required_integration="whatsapp",
    ),
    # Tier B: the underlying service (BookingService.create_lead_booking)
    # requires an already-resolved lead_id, and a serviglobal_managed
    # RuntimeSessionSpecV1 has no lead/contact resolution today. Documented
    # here so it slots in without a redesign once that resolution exists;
    # never selectable until it moves to status="available".
    ToolDefinition(
        key="calendar.create_booking",
        name="Crear cita",
        description="Crea una cita en el calendario del tenant para un lead ya identificado.",
        status="planned",
        input_schema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Fecha y hora deseada."},
            },
            "required": ["date"],
        },
        required_integration="booking",
    ),
    ToolDefinition(
        key="crm.create_lead",
        name="Crear lead",
        description="Crea un lead en el CRM a partir de los datos de contacto recogidos en la llamada.",
        status="planned",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre del contacto."},
                "phone": {"type": "string", "description": "Teléfono del contacto."},
            },
            "required": ["name", "phone"],
        },
        required_integration="crm",
    ),
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
