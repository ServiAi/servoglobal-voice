from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("ULTRAVOX_API_KEY", "test_ultravox_key")
os.environ.setdefault("AUTH0_DOMAIN", "example.auth0.com")
os.environ.setdefault("AUTH0_AUDIENCE", "https://api.example.test")
os.environ["SERVIAI_TEST_SECRET_FALLBACK"] = "1"
TEST_DB_PATH = Path("serviai_platform_tool_contract_test.db")
os.environ["DATABASE_URL"] = f"sqlite:///./{TEST_DB_PATH.as_posix()}"

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.resolved_tool import from_platform
from app.domain.tool_registry import get_tool
from app.models.identity import Tenant
from app.models.integrations import TenantWhatsAppTemplate
from app.schemas.session_context import CallerContext, ContactContext, SessionContextV1
from app.services.platform_tool_contract_service import PlatformToolContractError, PlatformToolContractService

WHATSAPP_TOOL = get_tool("whatsapp.send_message")
CALENDAR_TOOL = get_tool("calendar.check_availability")


def _v2_config(**overrides) -> dict:
    config = {
        "contract_version": 2,
        "template_key": "booking_confirmation",
        "recipient": {"strategy": "contact_then_caller"},
        "variables": {
            "contact_name": {"source": "context", "path": "contact.name"},
            "appointment_date": {"source": "llm", "type": "string", "description": "Fecha"},
            "company_name": {"source": "fixed", "value": "ServiGlobal"},
        },
    }
    config.update(overrides)
    return config


class PlatformToolContractServiceTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        TEST_DB_PATH.unlink(missing_ok=True)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            tenant = Tenant(name="Tenant A", slug="tenant-a")
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            self.tenant_id = tenant.id

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)

    def _create_template(self, *, status: str = "approved", template_key: str = "booking_confirmation") -> None:
        with SessionLocal() as db:
            db.add(TenantWhatsAppTemplate(
                tenant_id=self.tenant_id, template_key=template_key, provider_template_name=template_key,
                name=template_key, category="utility", language="es",
                body="Hola {{contact_name}}, tu cita es {{appointment_date}}. {{company_name}}",
                status=status, source="tenant_authored", parameter_format="NAMED",
                components_json={"variable_keys": ["contact_name", "appointment_date", "company_name"]},
            ))
            db.commit()

    # -- compile_llm_schema --------------------------------------------------

    def test_compile_llm_schema_only_includes_llm_source_variables(self):
        with SessionLocal() as db:
            schema = PlatformToolContractService(db).compile_llm_schema(
                from_platform(WHATSAPP_TOOL), _v2_config()
            )
        self.assertEqual(set(schema["properties"]), {"appointment_date"})
        self.assertEqual(schema["required"], ["appointment_date"])
        self.assertNotIn("template_key", schema["properties"])
        self.assertNotIn("to_phone", schema["properties"])
        self.assertNotIn("contact_name", schema["properties"])
        self.assertNotIn("company_name", schema["properties"])

    def test_compile_llm_schema_is_a_passthrough_for_tools_without_binding_config(self):
        with SessionLocal() as db:
            schema = PlatformToolContractService(db).compile_llm_schema(from_platform(CALENDAR_TOOL), {})
        self.assertEqual(schema, CALENDAR_TOOL.input_schema)

    # -- validate_binding_config ---------------------------------------------

    def test_validate_binding_config_accepts_a_complete_v2_config(self):
        self._create_template()
        with SessionLocal() as db:
            PlatformToolContractService(db).validate_binding_config(
                self.tenant_id, from_platform(WHATSAPP_TOOL), _v2_config()
            )  # does not raise

    def test_validate_binding_config_rejects_missing_contract_version(self):
        self._create_template()
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(
                    self.tenant_id, from_platform(WHATSAPP_TOOL), {}
                )
        self.assertEqual(ctx.exception.code, "tool_binding_config_invalid")

    def test_validate_binding_config_rejects_template_not_found(self):
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(
                    self.tenant_id, from_platform(WHATSAPP_TOOL), _v2_config()
                )
        self.assertEqual(ctx.exception.code, "whatsapp_template_not_found")

    def test_validate_binding_config_rejects_template_not_approved(self):
        self._create_template(status="draft")
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(
                    self.tenant_id, from_platform(WHATSAPP_TOOL), _v2_config()
                )
        self.assertEqual(ctx.exception.code, "whatsapp_template_not_approved")

    def test_validate_binding_config_rejects_a_template_from_another_tenant(self):
        self._create_template()
        with SessionLocal() as db:
            other = Tenant(name="Tenant B", slug="tenant-b")
            db.add(other)
            db.commit()
            db.refresh(other)
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(other.id, from_platform(WHATSAPP_TOOL), _v2_config())
        self.assertEqual(ctx.exception.code, "whatsapp_template_not_found")

    def test_validate_binding_config_rejects_incomplete_variable_mapping(self):
        self._create_template()
        config = _v2_config(variables={"contact_name": {"source": "fixed", "value": "x"}})
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), config)
        self.assertEqual(ctx.exception.code, "whatsapp_variable_mapping_incomplete")

    def test_validate_binding_config_rejects_an_unknown_context_path(self):
        self._create_template()
        config = _v2_config(variables={
            **_v2_config()["variables"],
            "contact_name": {"source": "context", "path": "contact.secret_field"},
        })
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), config)
        self.assertEqual(ctx.exception.code, "whatsapp_variable_source_invalid")

    def test_validate_binding_config_rejects_an_llm_variable_without_a_type(self):
        self._create_template()
        config = _v2_config(variables={
            **_v2_config()["variables"],
            "appointment_date": {"source": "llm", "description": "Fecha"},
        })
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), config)
        self.assertEqual(ctx.exception.code, "whatsapp_variable_source_invalid")

    def test_validate_binding_config_rejects_a_fixed_variable_without_a_value(self):
        self._create_template()
        config = _v2_config(variables={**_v2_config()["variables"], "company_name": {"source": "fixed"}})
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), config)
        self.assertEqual(ctx.exception.code, "whatsapp_variable_source_invalid")

    def test_validate_binding_config_rejects_an_invalid_recipient_strategy(self):
        self._create_template()
        config = _v2_config(recipient={"strategy": "anywhere"})
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), config)
        self.assertEqual(ctx.exception.code, "tool_binding_config_invalid")

    # -- resolve_whatsapp_send ------------------------------------------------

    def _invocation(self, *, llm_args=None, context=None, config=None):
        from app.domain.platform_tool_invocation import PlatformToolInvocation

        return PlatformToolInvocation(
            llm_args=llm_args if llm_args is not None else {"appointment_date": "2026-09-25"},
            context=context or SessionContextV1(
                caller=CallerContext(phone="+573000000001"),
                contact=ContactContext(id="contact-0", name="Cliente Default"),
            ),
            config=config if config is not None else _v2_config(),
        )

    def test_resolve_whatsapp_send_rejects_a_legacy_binding(self):
        self._create_template()
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).resolve_whatsapp_send(self.tenant_id, self._invocation(config={}))
        self.assertEqual(ctx.exception.code, "whatsapp_legacy_binding_unsupported")

    def test_resolve_whatsapp_send_prefers_contact_phone_over_caller_phone(self):
        self._create_template()
        context = SessionContextV1(
            caller=CallerContext(phone="+573000000001"),
            contact=ContactContext(id="contact-1", name="Carlos", phone="+573000000099"),
        )
        with SessionLocal() as db:
            plan = PlatformToolContractService(db).resolve_whatsapp_send(
                self.tenant_id, self._invocation(context=context)
            )
        self.assertEqual(plan.to_phone, "+573000000099")
        self.assertEqual(plan.variables["contact_name"], "Carlos")
        self.assertEqual(plan.variables["company_name"], "ServiGlobal")
        self.assertEqual(plan.variables["appointment_date"], "2026-09-25")
        self.assertEqual(plan.contact_id, "contact-1")

    def test_resolve_whatsapp_send_falls_back_to_caller_phone(self):
        self._create_template()
        context = SessionContextV1(
            caller=CallerContext(phone="+573000000001"),
            contact=ContactContext(id="contact-1", name="Carlos"),  # no contact.phone -> falls back
        )
        with SessionLocal() as db:
            plan = PlatformToolContractService(db).resolve_whatsapp_send(
                self.tenant_id, self._invocation(context=context, llm_args={"appointment_date": "2026-09-25"})
            )
        self.assertEqual(plan.to_phone, "+573000000001")

    def test_resolve_whatsapp_send_fails_without_any_trusted_phone(self):
        self._create_template()
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).resolve_whatsapp_send(
                    self.tenant_id, self._invocation(context=SessionContextV1())
                )
        self.assertEqual(ctx.exception.code, "whatsapp_recipient_context_required")

    def test_resolve_whatsapp_send_fails_when_llm_argument_is_missing(self):
        self._create_template()
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).resolve_whatsapp_send(
                    self.tenant_id, self._invocation(llm_args={})
                )
        self.assertEqual(ctx.exception.code, "tool_argument_invalid")

    def test_resolve_whatsapp_send_fails_when_context_variable_value_is_missing(self):
        self._create_template()
        context = SessionContextV1(caller=CallerContext(phone="+573000000001"))  # no contact.name
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).resolve_whatsapp_send(
                    self.tenant_id, self._invocation(context=context)
                )
        self.assertEqual(ctx.exception.code, "tool_context_value_missing")

    def test_resolve_whatsapp_send_reflects_the_templates_current_approval_status(self):
        # A binding validated at publish time can still fail at dispatch
        # time if the template was unsynced/unapproved afterwards.
        self._create_template()
        with SessionLocal() as db:
            PlatformToolContractService(db).validate_binding_config(self.tenant_id, from_platform(WHATSAPP_TOOL), _v2_config())
            template = db.query(TenantWhatsAppTemplate).filter_by(tenant_id=self.tenant_id).one()
            template.status = "pending"
            db.commit()
        context = SessionContextV1(
            caller=CallerContext(phone="+573000000001"),
            contact=ContactContext(id="contact-1", name="Carlos"),
        )
        with SessionLocal() as db:
            with self.assertRaises(PlatformToolContractError) as ctx:
                PlatformToolContractService(db).resolve_whatsapp_send(
                    self.tenant_id, self._invocation(context=context)
                )
        self.assertEqual(ctx.exception.code, "whatsapp_template_not_approved")


if __name__ == "__main__":
    unittest.main()
