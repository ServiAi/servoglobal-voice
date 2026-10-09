"""Architecture tests of Integrations / Messaging (the eighth real module)."""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
import subprocess
import sys
import typing
import unittest
from pathlib import Path

from sqlalchemy.orm import Session

APP = Path(__file__).resolve().parent / "app"
MODULE = APP / "modules" / "integrations"
MODELS_MODULE = "app.modules.integrations.infrastructure.models"

OWNED_TABLES = {
    "tenant_integrations",
    "tenant_integration_events",
    "tenant_whatsapp_configs",
    "tenant_whatsapp_templates",
    "tenant_whatsapp_flows",
    "crm_whatsapp_messages",
    "tenant_email_configs",
    "tenant_email_templates",
    "tenant_email_assets",
    "tenant_email_sends",
    "tenant_email_send_assets",
    "tenant_chatwoot_configs",
    "tenant_chatwoot_inboxes",
}
# Not Messaging's: they stay in app.models.integrations until Forms / Voice config become modules.
RESIDUAL_TABLES = {
    "tenant_forms",
    "tenant_form_fields",
    "tenant_form_tokens",
    "tenant_form_submissions",
    "tenant_form_submission_answers",
    "tenant_voice_provider_configs",
    "tenant_voice_agent_configs",
}
LEGACY_PATHS = [
    "services/integration_service.py",
    "services/integration_event_service.py",
    "services/whatsapp_client.py",
    "services/whatsapp_config_service.py",
    "services/whatsapp_template_service.py",
    "services/whatsapp_message_service.py",
    "services/whatsapp_flow_service.py",
    "services/whatsapp_flow_compiler.py",
    "services/whatsapp_flow_context_adapter.py",
    "services/email_config_service.py",
    "services/email_template_service.py",
    "services/email_send_service.py",
    "services/email_asset_service.py",
    "services/email_render_service.py",
    "services/resend_service.py",
    "services/chatwoot_config_service.py",
    "services/chatwoot_client.py",
    "services/chatwoot_platform_client.py",
    "models/crm.py",
    "api/endpoints/integrations.py",
    "api/endpoints/whatsapp_webhook.py",
    "api/endpoints/whatsapp_flows.py",
    "api/endpoints/email_assets.py",
    "api/endpoints/chatwoot_webhook.py",
    "schemas/whatsapp_flows.py",
]
PROVIDER_ERROR_NAMES = (
    "WhatsAppCloudClientError",
    "ResendServiceError",
    "ChatwootClientError",
    "ChatwootPlatformError",
)
SECRET_FIELD_WORDS = ("token", "secret", "password", "api_key", "authorization", "credential")

# The composition root may reach these legacy owners until they become modules (documented in wiring.py).
WIRING_LEGACY_ALLOWED = {
    "app.models.integrations",  # TenantFormToken (Forms)
    "app.services.call_summary_service",
    "app.services.onboarding_service",  # Identity
    "app.services.secret_manager_service",
    "app.services.storage_service",
    "app.services.voice_config_service",  # Voice Legacy (catalog status)
}
# Other modules Integrations may talk to, always through their public API.
FOREIGN_PUBLIC_ALLOWED = {
    "app.modules.crm.public",
    "app.modules.identity.public",
    "app.modules.notifications.public",
    "app.modules.scheduling.public",
    "app.modules.voice_experiences.public",
}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _import_targets(path: Path) -> set[str]:
    """Imported module names, plus ``module.name`` for ``from module import name`` (catches
    ``from app.services import notification_service``)."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _importers(target: str) -> set[str]:
    """App files (relative, forward slashes, excluding the target itself) importing ``target``."""
    own = target.replace(".", "/").removeprefix("app/") + ".py"
    return {
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if path.relative_to(APP).as_posix() != own and target in _import_targets(path)
    }


def _layer(layer: str) -> list[Path]:
    return sorted((MODULE / layer).rglob("*.py"))


def _starts(names: set[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted(n for n in names if n.startswith(prefixes))


class IntegrationsLayerBoundaryTests(unittest.TestCase):
    def test_public_import_is_light_in_a_clean_process(self) -> None:
        code = """
import sys
import app.modules.integrations.public
forbidden = (
    'app.modules.integrations.application',
    'app.modules.integrations.infrastructure',
    'app.modules.integrations.api',
    'app.modules.integrations.wiring',
    'app.modules.crm',
    'app.modules.notifications',
    'app.models',
    'app.services',
    'app.db',
    'sqlalchemy.orm',
    'fastapi',
    'httpx',
)
loaded = sorted(n for n in sys.modules if any(n == p or n.startswith(p + '.') for p in forbidden))
assert not loaded, loaded
"""
        subprocess.run([sys.executable, "-c", code], cwd=APP.parent, check=True)

    def test_application_has_no_provider_framework_or_foreign_internals(self) -> None:
        forbidden = (
            "httpx",
            "fastapi",
            "starlette",
            "app.services",
            "app.models",
            "app.modules.integrations.infrastructure.whatsapp",
            "app.modules.integrations.infrastructure.email",
            "app.modules.integrations.infrastructure.chatwoot",
            "app.modules.integrations.api",  # layers point inward: api -> application, never the reverse
            "app.modules.crm.application",
            "app.modules.crm.infrastructure",
            "app.modules.crm.domain",
            "app.modules.crm.wiring",
            "app.modules.notifications.application",
            "app.modules.notifications.infrastructure",
            "app.modules.notifications.domain",
            "app.modules.scheduling.application",
            "app.modules.scheduling.infrastructure",
            "app.modules.voice",
            "app.modules.agents",
            "app.modules.tools",
        )
        offenders = [
            f"{path.relative_to(APP)}: {name}"
            for path in _layer("application")
            for name in _starts(_imports(path), forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_application_does_not_name_provider_specific_errors(self) -> None:
        offenders = [
            f"{path.relative_to(APP)}: {name}"
            for path in _layer("application")
            for name in PROVIDER_ERROR_NAMES
            if re.search(rf"\b{name}\b", path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [], "map provider errors to ProviderError subclasses in infrastructure")

    def test_application_does_not_read_secrets_through_the_secret_manager(self) -> None:
        offenders = [
            str(path.relative_to(APP))
            for path in _layer("application")
            if "SecretManager" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(offenders, [])

    def test_provider_http_clients_live_only_in_infrastructure(self) -> None:
        offenders = [
            str(path.relative_to(APP))
            for path in MODULE.rglob("*.py")
            if "infrastructure" not in path.relative_to(MODULE).parts
            and any(name == "httpx" or name.startswith("httpx.") for name in _imports(path))
        ]
        self.assertEqual(offenders, [])
        for adapter in ("whatsapp/meta_client.py", "email/resend.py", "chatwoot/client.py", "chatwoot/platform_client.py"):
            self.assertTrue((MODULE / "infrastructure" / adapter).exists(), adapter)

    def test_provider_adapters_do_not_know_application_or_foreign_modules(self) -> None:
        forbidden = (
            "app.modules.integrations.application",
            "app.modules.integrations.api",
            "app.modules.integrations.wiring",
            "app.modules.crm",
            "app.modules.notifications",
            "app.services",
            "app.models",
        )
        offenders = [
            f"{path.relative_to(APP)}: {name}"
            for path in _layer("infrastructure")
            for name in _starts(_imports(path), forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_only_wiring_and_public_reach_other_modules_and_only_through_their_public_api(self) -> None:
        offenders: list[str] = []
        for path in MODULE.rglob("*.py"):
            for name in _imports(path):
                if not name.startswith("app.modules.") or name.startswith("app.modules.integrations"):
                    continue
                is_http_auth_edge = (
                    name == "app.modules.identity.api.deps" and path.relative_to(MODULE).parts[0] == "api"
                )
                if name not in FOREIGN_PUBLIC_ALLOWED and not is_http_auth_edge:
                    offenders.append(f"{path.relative_to(APP)} -> {name}")
        self.assertEqual(offenders, [])

    def test_legacy_owners_are_reached_only_from_wiring(self) -> None:
        legacy = ("app.models.integrations", "app.models.voice_context", "app.services")
        offenders: list[str] = []
        for path in MODULE.rglob("*.py"):
            if path.name == "wiring.py" and path.parent == MODULE:
                continue
            offenders += [f"{path.relative_to(APP)} -> {name}" for name in _starts(_imports(path), legacy)]
        self.assertEqual(offenders, [])
        wiring_legacy = {
            name
            for name in _starts(
                {
                    node.module
                    for node in ast.walk(ast.parse((MODULE / "wiring.py").read_text(encoding="utf-8")))
                    if isinstance(node, ast.ImportFrom) and node.module
                },
                legacy,
            )
        }
        self.assertLessEqual(wiring_legacy, WIRING_LEGACY_ALLOWED)

    def test_application_may_default_ports_only_through_wiring(self) -> None:
        for path in _layer("domain"):
            self.assertNotIn("app.modules.integrations.wiring", _imports(path), path.name)
        for path in _layer("infrastructure"):
            self.assertNotIn("app.modules.integrations.wiring", _imports(path), path.name)

    def test_no_foreign_code_reaches_integrations_internals(self) -> None:
        allowed = {APP / "main.py", APP / "models" / "__init__.py"}
        offenders: list[str] = []
        for path in APP.rglob("*.py"):
            if path.is_relative_to(MODULE) or path in allowed:
                continue
            offenders += [
                f"{path.relative_to(APP)} -> {name}"
                for name in _starts(
                    _imports(path),
                    tuple(f"app.modules.integrations.{layer}" for layer in ("application", "domain", "infrastructure", "api", "wiring")),
                )
            ]
        self.assertEqual(offenders, [])

    def test_main_mounts_only_the_modules_routers(self) -> None:
        imports = _imports(APP / "main.py")
        self.assertIn("app.modules.integrations.api", imports)
        self.assertFalse([n for n in imports if n.startswith("app.api.endpoints.") and "integrations" in n.split(".")[-1] and "voice" not in n])

    def test_legacy_paths_are_gone_without_shims(self) -> None:
        for relative in LEGACY_PATHS:
            self.assertFalse((APP / relative).exists(), relative)
        marker = "TEMPORARY compatibility shim"
        for path in APP.rglob("*.py"):
            self.assertNotIn(marker, path.read_text(encoding="utf-8"), path)
        offenders = [
            f"{path.relative_to(APP)} -> {name}"
            for path in APP.rglob("*.py")
            for name in _imports(path)
            if re.match(
                r"app\.services\.(whatsapp_|email_|resend_|chatwoot_|integration_)", name
            )
            or name in {"app.models.crm", "app.schemas.whatsapp_flows"}
        ]
        self.assertEqual(offenders, [])

    def test_meta_client_is_only_used_by_the_legacy_notification_workflow(self) -> None:
        # Global env-configured Meta credentials, hardcoded owner phones and fixed templates: a legacy demo
        # workflow that is neither tenant-scoped nor part of Integrations. It must not gain consumers.
        self.assertEqual(_importers("app.services.meta_client"), {"services/notification_service.py"})

    def test_legacy_notification_service_is_surrounded_not_spread(self) -> None:
        self.assertEqual(
            _importers("app.services.notification_service"),
            {"api/endpoints/notifications.py", "api/endpoints/voice.py"},
        )

    def test_no_real_module_depends_on_the_legacy_notification_workflow(self) -> None:
        offenders = [
            f"{path.relative_to(APP)} -> {target}"
            for path in (APP / "modules").rglob("*.py")
            for target in _import_targets(path)
            if target in {"app.services.notification_service", "app.services.meta_client"}
        ]
        self.assertEqual(offenders, [])

    def test_legacy_workflow_stays_out_of_the_integrations_module(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in MODULE.rglob("*.py"))
        for legacy_marker in ("OWNER_PHONES", "alerta_lead_owner", "cita_confirmada_cliente", "demo-iniciada"):
            self.assertNotIn(legacy_marker, text)

    def test_legacy_notification_routes_keep_their_contract(self) -> None:
        from app.main import app

        routes = {
            (method.upper(), path) for path, operations in app.openapi()["paths"].items() for method in operations
        }
        for expected in (
            ("POST", "/api/v1/notifications/booking"),
            ("GET", "/api/v1/notifications/webhook"),
            ("POST", "/api/v1/notifications/webhook"),
            ("GET", "/api/v1/webhook/whatsapp"),
            ("POST", "/api/v1/webhook/whatsapp"),
        ):
            self.assertIn(expected, routes)


class IntegrationsOwnershipTests(unittest.TestCase):
    def test_thirteen_tables_are_declared_only_in_the_module_models(self) -> None:
        import app.models  # noqa: F401  (registers every model)
        from app.db.base import Base

        by_table = {
            mapper.local_table.name: mapper.class_.__module__
            for mapper in Base.registry.mappers
            if hasattr(mapper.local_table, "name")
        }
        self.assertEqual({t for t in OWNED_TABLES if by_table.get(t) == MODELS_MODULE}, OWNED_TABLES)
        self.assertEqual({t for t, mod in by_table.items() if mod == MODELS_MODULE}, OWNED_TABLES)
        self.assertEqual(len(OWNED_TABLES), 13)

    def test_crm_whatsapp_messages_belongs_to_messaging_and_is_registered_once(self) -> None:
        import app.models  # noqa: F401
        from app.db.base import Base

        self.assertIn("crm_whatsapp_messages", Base.metadata.tables)
        declaring = [m.class_ for m in Base.registry.mappers if m.local_table.name == "crm_whatsapp_messages"]
        self.assertEqual([c.__module__ for c in declaring], [MODELS_MODULE])
        self.assertFalse((APP / "models" / "crm.py").exists())

    def test_residual_legacy_model_module_keeps_only_forms_and_voice_config(self) -> None:
        tree = ast.parse((APP / "models" / "integrations.py").read_text(encoding="utf-8"))
        tables = set()
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign) and any(getattr(t, "id", "") == "__tablename__" for t in item.targets):
                        tables.add(item.value.value)
        self.assertEqual(tables, RESIDUAL_TABLES)
        self.assertFalse(tables & OWNED_TABLES)

    def test_models_import_is_restricted_to_the_module_and_the_alembic_registry(self) -> None:
        allowed = {APP / "models" / "__init__.py"}
        offenders = [
            str(path.relative_to(APP))
            for path in APP.rglob("*.py")
            if not path.is_relative_to(MODULE)
            and path not in allowed
            and any(name.startswith(MODELS_MODULE) for name in _imports(path))
        ]
        self.assertEqual(offenders, [])

    def test_models_keep_foreign_keys_but_no_cross_module_orm_navigation(self) -> None:
        import app.models  # noqa: F401
        from app.db.base import Base

        problems = []
        for mapper in Base.registry.mappers:
            if mapper.class_.__module__ != MODELS_MODULE:
                continue
            for relationship in mapper.relationships:
                target = relationship.mapper.class_
                if target.__module__ != MODELS_MODULE:
                    problems.append(f"{mapper.class_.__name__}.{relationship.key} -> {target.__name__}")
        self.assertEqual(problems, [])
        message = Base.metadata.tables["crm_whatsapp_messages"]
        self.assertEqual(
            {fk.target_fullname for fk in message.foreign_keys},
            {
                "tenants.id",
                "crm_leads.id",
                "crm_contacts.id",
                "tenant_whatsapp_templates.id",
                "notification_deliveries.id",
            },
        )

    def test_models_use_the_shared_db_mixins_not_identity_reexports(self) -> None:
        imports = _imports(MODULE / "infrastructure" / "models.py")
        self.assertIn("app.db.mixins", imports)
        self.assertNotIn("app.models.identity", imports)


class IntegrationsPublicApiTests(unittest.TestCase):
    def _public(self):
        import importlib

        return importlib.import_module("app.modules.integrations.public")

    def test_public_dtos_are_frozen_and_carry_no_orm_or_secrets(self) -> None:
        from app.db.base import Base

        public = self._public()
        dtos = [
            getattr(public, name)
            for name in public.__all__
            if dataclasses.is_dataclass(getattr(public, name))
        ]
        self.assertGreaterEqual(len(dtos), 10)
        for cls in dtos:
            self.assertTrue(cls.__dataclass_params__.frozen, cls.__name__)
            hints = typing.get_type_hints(cls, vars(public))
            for field in dataclasses.fields(cls):
                lowered = field.name.lower()
                self.assertFalse(
                    any(word in lowered for word in SECRET_FIELD_WORDS), f"{cls.__name__}.{field.name} looks like a secret"
                )
                self.assertNotIn(Base, getattr(hints[field.name], "__mro__", ()), f"{cls.__name__}.{field.name}")

    def test_chatwoot_gateway_is_typed_and_exposes_no_provider_type(self) -> None:
        import inspect

        public = self._public()
        for cls in (public.ChatwootFacade, public.ChatwootGateway):
            for name, member in vars(cls).items():
                if not callable(member) or (name.startswith("_") and name != "__init__"):
                    continue
                hints = typing.get_type_hints(member, {**vars(public), "Session": Session})
                for parameter, annotation in hints.items():
                    where = f"{cls.__name__}.{name}({parameter})"
                    self.assertIsNot(annotation, typing.Any, where)
                    module = getattr(annotation, "__module__", "") or ""
                    self.assertNotIn("infrastructure", module, where)
                    self.assertFalse(module.startswith(("httpx", "app.modules.integrations.domain.chatwoot")), where)
        client_hint = typing.get_type_hints(public.ChatwootGateway.__init__, vars(public))["client"]
        self.assertTrue(inspect.isclass(client_hint) and typing.Protocol in client_hint.__mro__)

    def test_chatwoot_client_satisfies_the_gateway_protocol_structurally(self) -> None:
        from app.modules.integrations.infrastructure.chatwoot.client import ChatwootClient

        public = self._public()
        protocol = typing.get_type_hints(public.ChatwootGateway.__init__, vars(public))["client"]
        for name in ("get_or_create_contact", "get_or_create_conversation", "assign_team", "send_message", "add_label"):
            self.assertTrue(inspect.iscoroutinefunction(getattr(ChatwootClient, name)), name)
            self.assertEqual(
                list(inspect.signature(getattr(protocol, name)).parameters),
                list(inspect.signature(getattr(ChatwootClient, name)).parameters),
                name,
            )

    def test_public_facades_exist(self) -> None:
        public = self._public()
        for name in ("IntegrationsFacade", "IntegrationEvents", "WhatsAppFacade", "EmailFacade", "ChatwootFacade"):
            self.assertTrue(hasattr(public, name), name)

    def test_public_events_api_mirrors_the_audit_service(self) -> None:
        public = self._public()
        self.assertTrue(callable(public.IntegrationEvents.record))
        self.assertTrue(callable(public.IntegrationEvents.add))


if __name__ == "__main__":
    unittest.main()
