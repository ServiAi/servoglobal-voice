from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


LocalizedText = dict[str, str]


@dataclass(frozen=True)
class NotificationEventField:
    path: str
    label: LocalizedText
    group: LocalizedText
    description: LocalizedText
    data_type: str
    example: Any
    operators: tuple[str, ...]
    formats: tuple[str, ...] = ("string",)
    nullable: bool = False
    enum_values: tuple[str, ...] = ()
    recipient_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["operators"] = list(self.operators)
        data["formats"] = list(self.formats)
        data["enum_values"] = list(self.enum_values)
        return data


@dataclass(frozen=True)
class NotificationEventSchema:
    capability_key: str
    event_type: str
    label: LocalizedText
    description: LocalizedText
    version: int
    fields: tuple[NotificationEventField, ...]
    example_payload: dict[str, Any]

    def field(self, path: str) -> NotificationEventField | None:
        return next((field for field in self.fields if field.path == path), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_key": self.capability_key,
            "event_type": self.event_type,
            "label": self.label,
            "description": self.description,
            "version": self.version,
            "fields": [field.to_dict() for field in self.fields],
            "recipient_paths": [field.path for field in self.fields if field.recipient_eligible],
            "example_payload": self.example_payload,
        }


class NotificationEventSchemaError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_PRESENCE = ("exists", "not_exists")
_EMPTY = ("is_empty", "not_empty")
_STRING = ("equals", "not_equals", "in", "not_in", "contains", "starts_with", "ends_with") + _PRESENCE + _EMPTY
_ENUM = ("equals", "not_equals", "in", "not_in") + _PRESENCE
_NUMBER = (
    "equals",
    "not_equals",
    "in",
    "not_in",
    "greater_than",
    "greater_than_or_equal",
    "less_than",
    "less_than_or_equal",
) + _PRESENCE
_BOOLEAN = ("equals", "not_equals") + _PRESENCE
_DATETIME = _NUMBER
_DATE_FORMATS = ("string", "date_iso", "date_dmy", "time_24h", "datetime_iso", "datetime_dmy_24h")

_GROUP_BOOKING = {"es": "Reserva", "en": "Booking"}
_GROUP_CUSTOMER = {"es": "Cliente", "en": "Customer"}
_GROUP_LEAD = {"es": "Lead", "en": "Lead"}
_GROUP_CALL = {"es": "Llamada", "en": "Call"}


def _field(
    path: str,
    es: str,
    en: str,
    group: LocalizedText,
    data_type: str,
    example: Any,
    *,
    nullable: bool = False,
    enum_values: tuple[str, ...] = (),
    recipient_eligible: bool = False,
) -> NotificationEventField:
    operators = {
        "string": _STRING,
        "enum": _ENUM,
        "number": _NUMBER,
        "boolean": _BOOLEAN,
        "datetime": _DATETIME,
    }[data_type]
    return NotificationEventField(
        path=path,
        label={"es": es, "en": en},
        group=group,
        description={"es": f"Dato disponible en {path}.", "en": f"Data available at {path}."},
        data_type=data_type,
        example=example,
        operators=operators,
        formats=_DATE_FORMATS if data_type == "datetime" else ("string",),
        nullable=nullable,
        enum_values=enum_values,
        recipient_eligible=recipient_eligible,
    )


_BOOKING_FIELDS = (
    _field("booking.id", "ID de la reserva", "Booking ID", _GROUP_BOOKING, "string", "booking-demo-001"),
    _field(
        "booking.status",
        "Estado de la reserva",
        "Booking status",
        _GROUP_BOOKING,
        "enum",
        "scheduled",
        enum_values=("pending", "accepted", "scheduled", "confirmed", "rescheduled", "cancelled", "completed", "failed"),
    ),
    _field("booking.title", "Título", "Title", _GROUP_BOOKING, "string", "Consulta inicial", nullable=True),
    _field("booking.start_at", "Inicio", "Start time", _GROUP_BOOKING, "datetime", "2026-08-12T15:00:00+00:00"),
    _field("booking.end_at", "Fin", "End time", _GROUP_BOOKING, "datetime", "2026-08-12T15:30:00+00:00", nullable=True),
    _field("booking.timezone", "Zona horaria", "Timezone", _GROUP_BOOKING, "string", "America/Bogota"),
    _field("booking.meeting_url", "Enlace de reunión", "Meeting URL", _GROUP_BOOKING, "string", "https://example.test/meeting", nullable=True),
    _field("customer.name", "Nombre", "Name", _GROUP_CUSTOMER, "string", "Cliente Demo", nullable=True),
    _field("customer.phone", "Teléfono", "Phone", _GROUP_CUSTOMER, "string", "+573001112233", nullable=True, recipient_eligible=True),
    _field("customer.email", "Correo", "Email", _GROUP_CUSTOMER, "string", "cliente@example.test", nullable=True),
    _field("lead.id", "ID del lead", "Lead ID", _GROUP_LEAD, "string", "lead-demo-001", nullable=True),
    _field("lead.status", "Estado del lead", "Lead status", _GROUP_LEAD, "string", "qualified", nullable=True),
)

_CALL_FIELDS = (
    _field("call.id", "ID de la llamada", "Call ID", _GROUP_CALL, "string", "call-demo-001"),
    _field("call.provider", "Proveedor", "Provider", _GROUP_CALL, "string", "demo"),
    _field("call.provider_call_id", "ID del proveedor", "Provider call ID", _GROUP_CALL, "string", "provider-demo-001", nullable=True),
    _field("call.status", "Estado", "Status", _GROUP_CALL, "enum", "completed", enum_values=("completed", "failed", "no_answer", "busy")),
    _field("call.duration_seconds", "Duración en segundos", "Duration in seconds", _GROUP_CALL, "number", 180, nullable=True),
    _field("call.summary", "Resumen", "Summary", _GROUP_CALL, "string", "Llamada de demostración", nullable=True),
    _field("call.outcome", "Resultado", "Outcome", _GROUP_CALL, "string", "completed", nullable=True),
    _field("customer.name", "Nombre", "Name", _GROUP_CUSTOMER, "string", "Cliente Demo", nullable=True),
    _field("customer.phone", "Teléfono", "Phone", _GROUP_CUSTOMER, "string", "+573001112233", nullable=True, recipient_eligible=True),
    _field("customer.email", "Correo", "Email", _GROUP_CUSTOMER, "string", "cliente@example.test", nullable=True),
    _field("lead.id", "ID del lead", "Lead ID", _GROUP_LEAD, "string", "lead-demo-001", nullable=True),
    _field("lead.status", "Estado del lead", "Lead status", _GROUP_LEAD, "string", "qualified", nullable=True),
)

_BOOKING_EXAMPLE = {
    "booking": {
        "id": "booking-demo-001",
        "status": "scheduled",
        "title": "Consulta inicial",
        "start_at": "2026-08-12T15:00:00+00:00",
        "end_at": "2026-08-12T15:30:00+00:00",
        "timezone": "America/Bogota",
        "meeting_url": "https://example.test/meeting",
    },
    "customer": {"name": "Cliente Demo", "phone": "+573001112233", "email": "cliente@example.test"},
    "lead": {"id": "lead-demo-001", "status": "qualified"},
    "custom": {},
}

_CALL_EXAMPLE = {
    "call": {
        "id": "call-demo-001",
        "provider": "demo",
        "provider_call_id": "provider-demo-001",
        "status": "completed",
        "duration_seconds": 180,
        "summary": "Llamada de demostración",
        "outcome": "completed",
    },
    "customer": {"name": "Cliente Demo", "phone": "+573001112233", "email": "cliente@example.test"},
    "lead": {"id": "lead-demo-001", "status": "qualified"},
    "custom": {},
}


def _schema(event_type: str, es: str, en: str, fields: tuple[NotificationEventField, ...], example: dict[str, Any]) -> NotificationEventSchema:
    capability_key = "booking_notifications" if event_type.startswith("booking.") else "call_notifications"
    return NotificationEventSchema(
        capability_key=capability_key,
        event_type=event_type,
        label={"es": es, "en": en},
        description={"es": f"Contrato de datos para {event_type}.", "en": f"Data contract for {event_type}."},
        version=1,
        fields=fields,
        example_payload=example,
    )


_SCHEMAS = {
    schema.event_type: schema
    for schema in (
        _schema("booking.created", "Reserva creada", "Booking created", _BOOKING_FIELDS, _BOOKING_EXAMPLE),
        _schema("booking.cancelled", "Reserva cancelada", "Booking cancelled", _BOOKING_FIELDS, _BOOKING_EXAMPLE),
        _schema("booking.rescheduled", "Reserva reprogramada", "Booking rescheduled", _BOOKING_FIELDS, _BOOKING_EXAMPLE),
        _schema("call.completed", "Llamada completada", "Call completed", _CALL_FIELDS, _CALL_EXAMPLE),
        _schema("call.failed", "Llamada fallida", "Call failed", _CALL_FIELDS, _CALL_EXAMPLE),
        _schema("call.no_answer", "Llamada sin respuesta", "Call unanswered", _CALL_FIELDS, _CALL_EXAMPLE),
    )
}


def list_notification_event_schemas(capability_key: str | None = None) -> list[NotificationEventSchema]:
    schemas = _SCHEMAS.values()
    if capability_key is not None:
        schemas = (schema for schema in schemas if schema.capability_key == capability_key)
    return sorted(schemas, key=lambda schema: schema.event_type)


def get_notification_event_schema(capability_key: str, event_type: str) -> NotificationEventSchema | None:
    schema = _SCHEMAS.get(event_type)
    return schema if schema is not None and schema.capability_key == capability_key else None


def notification_capabilities_metadata() -> list[dict[str, Any]]:
    return [
        {
            "key": "booking_notifications",
            "label": {"es": "Notificaciones de reservas", "en": "Booking notifications"},
            "events": [schema.event_type for schema in list_notification_event_schemas("booking_notifications")],
        },
        {
            "key": "call_notifications",
            "label": {"es": "Notificaciones de llamadas", "en": "Call notifications"},
            "events": [schema.event_type for schema in list_notification_event_schemas("call_notifications")],
        },
    ]


def validate_rule_event_schema(rule: Any, conditions: list[Any]) -> NotificationEventSchema:
    schema = get_notification_event_schema(rule.capability_key, rule.event_type)
    if schema is None:
        raise NotificationEventSchemaError("unsupported_capability_event_pair")
    if getattr(rule, "conditions_mode", "all") not in {"all", "any"}:
        raise NotificationEventSchemaError("unsupported_conditions_mode")

    for condition in conditions:
        field = schema.field(condition.field)
        if field is None:
            if condition.field.startswith("custom."):
                continue
            raise NotificationEventSchemaError("condition_field_not_in_event_schema")
        operator = getattr(condition.operator, "value", condition.operator)
        if operator not in field.operators:
            raise NotificationEventSchemaError("condition_operator_not_allowed_for_field")
        _validate_condition_value(field, operator, condition.value)

    mapping = getattr(rule, "variable_mapping_json", {})
    if isinstance(mapping, dict):
        for raw_spec in mapping.values():
            if not isinstance(raw_spec, dict) or raw_spec.get("source") != "event_field":
                continue
            path = raw_spec.get("path")
            if not isinstance(path, str) or (schema.field(path) is None and not path.startswith("custom.")):
                raise NotificationEventSchemaError("variable_path_not_in_event_schema")
            timezone_path = raw_spec.get("timezone_path")
            if timezone_path and schema.field(timezone_path) is None and not timezone_path.startswith("custom."):
                raise NotificationEventSchemaError("variable_timezone_path_not_in_event_schema")

    if getattr(rule, "recipient_strategy", None) == "event_field":
        recipient_path = getattr(rule, "recipient_group_key", None)
        field = schema.field(recipient_path) if recipient_path else None
        if (field is None or not field.recipient_eligible) and not (
            isinstance(recipient_path, str) and recipient_path.startswith("custom.")
        ):
            raise NotificationEventSchemaError("recipient_path_not_allowed_for_event")
    return schema


def _validate_condition_value(field: NotificationEventField, operator: str, value: Any) -> None:
    if operator in _PRESENCE + _EMPTY:
        return
    values = value if operator in {"in", "not_in"} else [value]
    if not isinstance(values, list) or not values:
        raise NotificationEventSchemaError("condition_value_invalid_for_field")
    for item in values:
        if field.data_type == "number" and (isinstance(item, bool) or not isinstance(item, (int, float))):
            raise NotificationEventSchemaError("condition_numeric_value_required")
        if field.data_type == "boolean" and not isinstance(item, bool):
            raise NotificationEventSchemaError("condition_value_invalid_for_field")
        if field.data_type in {"string", "enum", "datetime"} and not isinstance(item, str):
            raise NotificationEventSchemaError("condition_value_invalid_for_field")
        if field.enum_values and item not in field.enum_values:
            raise NotificationEventSchemaError("condition_value_not_in_enum")
