from __future__ import annotations

from dataclasses import is_dataclass

from _integrations_2a_test_base import Integration2ATestCase
from app.db.session import SessionLocal
from app.models.integrations import TenantVoiceAgentConfig
from app.modules.integrations.application.ports import VoiceContextSchemaPort
from app.modules.integrations.domain.whatsapp_flow_context import (
    ContextFieldSnapshot,
    ContextSchemaSnapshot,
    builder_from_context_schema,
)
from app.modules.integrations.wiring import LegacyVoiceContextSchemas
from app.modules.voice_experiences.infrastructure.context_models import (
    TenantVoiceContextField,
    TenantVoiceContextSchema,
)
from app.modules.voice_experiences.public import (
    VoiceContextOptionSnapshot,
    VoiceContextSchemaSnapshot,
    create_context_schema_reader,
)

OPTIONS = [{"value": "sales", "label": "Ventas"}, {"value": "support", "label": "Soporte"}]


class VoiceContextSchemaAdapterTests(Integration2ATestCase):
    def setUp(self) -> None:
        super().setUp()
        with SessionLocal() as db:
            agent = TenantVoiceAgentConfig(
                tenant_id=self.tenant.id, provider="ultravox", provider_agent_id="agent", display_name="Agent", status="active"
            )
            db.add(agent)
            db.flush()
            schema = TenantVoiceContextSchema(
                tenant_id=self.tenant.id,
                agent_config_id=agent.id,
                schema_key="adapter",
                version=1,
                status="active",
                name="Adapter",
            )
            db.add(schema)
            db.flush()
            db.add(
                TenantVoiceContextField(
                    tenant_id=self.tenant.id,
                    schema_id=schema.id,
                    key="area",
                    label="Area",
                    field_type="select",
                    collection_mode="ask_if_missing",
                    required=True,
                    position=0,
                    sensitivity="standard",
                    validation_json={},
                    options_json=OPTIONS,
                )
            )
            db.commit()
            self.schema_id = schema.id

    def test_public_reader_returns_typed_option_dtos(self) -> None:
        with SessionLocal() as db:
            snapshot = create_context_schema_reader(db).get_schema_snapshot(self.tenant.id, self.schema_id)

        self.assertIsInstance(snapshot, VoiceContextSchemaSnapshot)
        options = snapshot.fields[0].options
        self.assertEqual(
            options,
            (VoiceContextOptionSnapshot("sales", "Ventas"), VoiceContextOptionSnapshot("support", "Soporte")),
        )
        self.assertTrue(all(is_dataclass(option) for option in options))

    def test_integrations_port_translates_to_its_own_snapshot_contract(self) -> None:
        with SessionLocal() as db:
            port: VoiceContextSchemaPort = LegacyVoiceContextSchemas(db)
            snapshot = port.get_schema_snapshot(self.tenant.id, self.schema_id)
            self.assertIsNone(port.get_schema_snapshot("other-tenant", self.schema_id))

        self.assertIsInstance(snapshot, ContextSchemaSnapshot)
        self.assertNotIsInstance(snapshot, VoiceContextSchemaSnapshot)
        field = snapshot.fields[0]
        self.assertIsInstance(field, ContextFieldSnapshot)
        self.assertEqual(field.options, tuple(OPTIONS))
        self.assertTrue(all(type(option) is dict for option in field.options))

    def test_whatsapp_flow_compiler_preserves_option_value_and_label(self) -> None:
        with SessionLocal() as db:
            snapshot = LegacyVoiceContextSchemas(db).get_schema_snapshot(self.tenant.id, self.schema_id)

        builder, context_snapshot = builder_from_context_schema(snapshot)

        select = next(item for item in builder["screens"][0]["components"] if item["id"] == "area")
        self.assertEqual(
            [(option["context_value"], option["title"]) for option in select["options"]],
            [("sales", "Ventas"), ("support", "Soporte")],
        )
        self.assertEqual(context_snapshot["fields"][0]["options"], OPTIONS)


if __name__ == "__main__":
    import unittest

    unittest.main()
