from __future__ import annotations

import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP = Path(__file__).resolve().parent / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


class NotificationsBoundaryTests(unittest.TestCase):
    def test_public_import_is_light_in_a_clean_process(self) -> None:
        code = """
import sys
import app.modules.notifications.public
forbidden = (
    'app.modules.notifications.application',
    'app.modules.notifications.infrastructure',
    'app.modules.notifications.api',
    'app.models.notifications',
    'app.models.integrations',
    'app.models.crm',
    'app.services.whatsapp_',
    'app.services.meta_',
    'app.services.chatwoot_',
    'fastapi',
)
loaded = [name for name in sys.modules if any(name == item or name.startswith(item) for item in forbidden)]
assert not loaded, loaded
"""
        subprocess.run([sys.executable, "-c", code], cwd=APP.parent, check=True)

    def test_domain_has_no_framework_persistence_or_service_imports(self) -> None:
        forbidden = ("sqlalchemy", "fastapi", "starlette", "app.models", "app.services", "app.db")
        imports = set().union(*(_imports(path) for path in (APP / "modules/notifications/domain").rglob("*.py")))
        self.assertFalse([name for name in imports if name.startswith(forbidden)])

    def test_application_has_no_provider_or_foreign_orm_imports(self) -> None:
        forbidden = (
            "app.services.whatsapp_",
            "app.services.meta_",
            "app.services.chatwoot_",
            "app.models.crm",
            "app.models.integrations",
            "app.modules.crm.application",
            "app.modules.crm.infrastructure",
            "app.modules.scheduling.application",
            "app.modules.scheduling.infrastructure",
        )
        files = (APP / "modules/notifications/application").rglob("*.py")
        imports = {name for path in files for name in _imports(path)}
        self.assertFalse([name for name in imports if name.startswith(forbidden)])

    def test_legacy_notification_model_and_service_paths_are_gone(self) -> None:
        files = list(APP.rglob("*.py"))
        imports = {name for path in files for name in _imports(path)}
        self.assertNotIn("app.models.notifications", imports)
        old_services = [
            name
            for name in imports
            if name.startswith("app.services.notification_") and name != "app.services.notification_service"
        ]
        self.assertEqual(old_services, [])

    def test_only_notification_module_and_registry_import_its_models(self) -> None:
        violations: list[str] = []
        for path in APP.rglob("*.py"):
            if path.is_relative_to(APP / "modules/notifications") or path == APP / "models/__init__.py":
                continue
            for name in _imports(path):
                if name.startswith("app.modules.notifications.infrastructure.models"):
                    violations.append(f"{path.relative_to(APP)} -> {name}")
        self.assertEqual(violations, [])

    def test_integrations_public_does_not_depend_on_notifications(self) -> None:
        imports = _imports(APP / "modules/integrations/public.py")
        self.assertFalse([name for name in imports if name.startswith("app.modules.notifications")])

    def test_whatsapp_channel_maps_public_contracts_to_notification_dtos(self) -> None:
        from app.modules.integrations.public import (
            WhatsAppFacade,
            WhatsAppMessageReceipt,
            WhatsAppSendOutcome,
            WhatsAppTemplateContract,
        )
        from app.modules.notifications.infrastructure.channel import IntegrationsWhatsAppChannel

        channel = IntegrationsWhatsAppChannel(object())
        contract = WhatsAppTemplateContract("reminder", "approved", ("first_name",), "Hola")
        with patch.object(WhatsAppFacade, "get_approved_template_contract", return_value=contract) as get_template:
            template = channel.get_template(tenant_id="tenant", template_key="reminder")
        get_template.assert_called_once_with("tenant", "reminder")
        self.assertEqual(template.required_variables, ("first_name",))
        self.assertEqual(template.body, "Hola")

        message = WhatsAppMessageReceipt(
            id="message-id",
            tenant_id="tenant",
            template_id="template-id",
            status="sent",
            metadata_json={},
            lead_id=None,
            contact_id=None,
            error_message=None,
            notification_delivery_id="delivery",
            delivered_at=None,
            read_at=None,
        )
        with patch.object(
            WhatsAppFacade,
            "send_template",
            return_value=WhatsAppSendOutcome("sent", "provider-id", "message-id", message),
        ) as send_template:
            result = channel.send_template(
                tenant_id="tenant",
                to_phone="573000000000",
                template_key="reminder",
                variables={"first_name": "Ana"},
                metadata={},
                notification_delivery_id="delivery",
                lead_id=None,
                contact_id=None,
            )
        self.assertEqual((result.status, result.message_id, result.provider_message_id),
                         ("sent", "message-id", "provider-id"))
        self.assertEqual(result.message.id, "message-id")
        send_template.assert_called_once()


if __name__ == "__main__":
    unittest.main()
