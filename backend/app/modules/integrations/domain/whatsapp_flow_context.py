from __future__ import annotations

import re

from app.models.voice_context import TenantVoiceContextSchema


FIELD_TYPE_MAP = {
    "text": "text_input",
    "textarea": "text_area",
    "email": "email_input",
    "phone": "phone_input",
    "integer": "number_input",
    "select": "dropdown",
    "checkbox": "checkbox",
    "date": "date",
}
VISIBLE_COLLECTION_MODES = {"ask_if_missing", "prefill_and_confirm"}


def builder_from_context_schema(schema: TenantVoiceContextSchema) -> tuple[dict, dict]:
    components: list[dict] = [
        {"id": "intro_heading", "type": "heading", "text": schema.name},
    ]
    if schema.description:
        components.append({"id": "intro_body", "type": "body", "text": schema.description})
    snapshot_fields: list[dict] = []
    for field in schema.fields:
        snapshot_fields.append(
            {
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "collection_mode": field.collection_mode,
                "required": field.required,
                "position": field.position,
                "options": field.options_json or [],
            }
        )
        if field.collection_mode not in VISIBLE_COLLECTION_MODES:
            continue
        component = {
            "id": field.key,
            "type": FIELD_TYPE_MAP[field.field_type],
            "label": field.label,
            "placeholder": field.description,
            "required": field.required,
            "binding": {
                "context_field_key": field.key,
                "prefill_supported_later": field.collection_mode == "prefill_and_confirm",
            },
        }
        if field.field_type == "select":
            component["options"] = [
                {
                    "id": value if re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", value) else f"option_{index + 1}",
                    "title": str(option["label"])[:30],
                    "context_value": value,
                }
                for index, option in enumerate(field.options_json or [])
                for value in [str(option["value"])]
            ]
        components.append(component)
    components.append(
        {
            "id": "submit",
            "type": "footer",
            "label": "Enviar",
            "action": {"type": "complete"},
        }
    )
    builder = {
        "version": 1,
        "screens": [{"id": "CONTEXT", "title": schema.name[:80], "terminal": True, "components": components}],
    }
    snapshot = {
        "schema_key": schema.schema_key,
        "version": schema.version,
        "name": schema.name,
        "description": schema.description,
        "fields": snapshot_fields,
    }
    return builder, snapshot


def blank_builder() -> dict:
    return {
        "version": 1,
        "screens": [
            {
                "id": "START",
                "title": "Nueva pantalla",
                "terminal": True,
                "components": [
                    {"id": "welcome", "type": "heading", "text": "Cuéntanos un poco más"},
                    {
                        "id": "submit",
                        "type": "footer",
                        "label": "Enviar",
                        "action": {"type": "complete"},
                    },
                ],
            }
        ],
    }
