import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

from app.services.chatwoot_client import ChatwootClientConfig
from app.services.notification_service import NotificationService

_TENANT_ID = "tenant-1"
_CLIENT_CONFIG = ChatwootClientConfig(
    base_url="https://crm.serviglobal-ia.com",
    account_id=17,
    api_token="token",
    default_inbox_id=35,
)


class NotificationServiceChatwootNotesTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_start_registers_chatwoot_note_from_form_context(self):
        service = NotificationService()
        note_mock = AsyncMock(return_value=True)

        with patch.object(service, "_crm_private_note", note_mock):
            ok = await service.notify_demo_start(
                db=None,
                tenant_id=_TENANT_ID,
                context={
                    "phone": "+573001112233",
                    "name": "Maria Demo",
                    "email": "maria@example.com",
                    "industry": "Inmobiliaria",
                    "useCase": "Calificar leads",
                    "volume": "50 llamadas",
                    "painPoint": "Seguimiento manual",
                },
            )

        self.assertTrue(ok)
        note_mock.assert_awaited_once()
        args, kwargs = note_mock.await_args
        self.assertEqual(args[0], None)
        self.assertEqual(args[1], _TENANT_ID)
        self.assertEqual(kwargs["phone"], "+573001112233")
        self.assertEqual(kwargs["contact_name"], "Maria Demo")
        self.assertEqual(kwargs["contact_email"], "maria@example.com")
        self.assertEqual(kwargs["labels"], ["demo-iniciada"])
        self.assertIn("Inmobiliaria", kwargs["note"])
        self.assertIn("Calificar leads", kwargs["note"])

    async def test_private_note_returns_false_when_chatwoot_rejects_message(self):
        service = NotificationService()
        fake_client = AsyncMock()
        fake_client.get_or_create_contact = AsyncMock(return_value=123)
        fake_client.get_or_create_conversation = AsyncMock(return_value=456)
        fake_client.send_message = AsyncMock(return_value=False)
        fake_client.add_label = AsyncMock(return_value=True)

        with patch(
            "app.services.notification_service.ChatwootConfigService.get_active_client_config",
            return_value=(object(), _CLIENT_CONFIG),
        ), patch("app.services.notification_service.ChatwootClient", return_value=fake_client):
            ok = await service._crm_private_note(
                None,
                _TENANT_ID,
                "+573001112233",
                "Nota de prueba",
                contact_name="Maria Demo",
                labels=["demo-iniciada"],
            )

        self.assertFalse(ok)
        fake_client.send_message.assert_awaited_once_with(456, "Nota de prueba", private=True)
        fake_client.add_label.assert_not_awaited()

    async def test_private_note_returns_true_after_message_is_created(self):
        service = NotificationService()
        fake_client = AsyncMock()
        fake_client.get_or_create_contact = AsyncMock(return_value=123)
        fake_client.get_or_create_conversation = AsyncMock(return_value=456)
        fake_client.send_message = AsyncMock(return_value=True)
        fake_client.add_label = AsyncMock(return_value=True)

        with patch(
            "app.services.notification_service.ChatwootConfigService.get_active_client_config",
            return_value=(object(), _CLIENT_CONFIG),
        ), patch("app.services.notification_service.ChatwootClient", return_value=fake_client):
            ok = await service._crm_private_note(
                None,
                _TENANT_ID,
                "+573001112233",
                "Nota de prueba",
                contact_name="Maria Demo",
                labels=["demo-iniciada"],
            )

        self.assertTrue(ok)
        fake_client.add_label.assert_awaited_once_with(456, ["demo-iniciada"])

    async def test_private_note_returns_false_when_chatwoot_not_configured(self):
        service = NotificationService()

        with patch(
            "app.services.notification_service.ChatwootConfigService.get_active_client_config",
            side_effect=ValueError("Chatwoot integration is not configured"),
        ):
            ok = await service._crm_private_note(
                None,
                _TENANT_ID,
                "+573001112233",
                "Nota de prueba",
            )

        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
