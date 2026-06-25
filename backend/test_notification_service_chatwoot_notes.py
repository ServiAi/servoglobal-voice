import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("ULTRAVOX_API_KEY", "test")

from app.services.notification_service import NotificationService


class NotificationServiceChatwootNotesTests(unittest.IsolatedAsyncioTestCase):
    async def test_demo_start_registers_chatwoot_note_from_form_context(self):
        service = NotificationService()
        note_mock = AsyncMock(return_value=True)

        with patch.object(service, "_crm_private_note", note_mock):
            ok = await service.notify_demo_start(
                {
                    "phone": "+573001112233",
                    "name": "Maria Demo",
                    "email": "maria@example.com",
                    "industry": "Inmobiliaria",
                    "useCase": "Calificar leads",
                    "volume": "50 llamadas",
                    "painPoint": "Seguimiento manual",
                }
            )

        self.assertTrue(ok)
        note_mock.assert_awaited_once()
        kwargs = note_mock.await_args.kwargs
        self.assertEqual(kwargs["phone"], "+573001112233")
        self.assertEqual(kwargs["contact_name"], "Maria Demo")
        self.assertEqual(kwargs["contact_email"], "maria@example.com")
        self.assertEqual(kwargs["labels"], ["demo-iniciada"])
        self.assertIn("Inmobiliaria", kwargs["note"])
        self.assertIn("Calificar leads", kwargs["note"])

    async def test_private_note_returns_false_when_chatwoot_rejects_message(self):
        service = NotificationService()
        fake_chatwoot = SimpleNamespace(
            api_token="token",
            get_or_create_contact=AsyncMock(return_value=123),
            get_or_create_conversation=AsyncMock(return_value=456),
            send_message=AsyncMock(return_value=False),
            add_label=AsyncMock(return_value=True),
        )

        with patch("app.services.notification_service.chatwoot_service", fake_chatwoot):
            ok = await service._crm_private_note(
                "+573001112233",
                "Nota de prueba",
                contact_name="Maria Demo",
                labels=["demo-iniciada"],
            )

        self.assertFalse(ok)
        fake_chatwoot.send_message.assert_awaited_once_with(456, "Nota de prueba", private=True)
        fake_chatwoot.add_label.assert_not_awaited()

    async def test_private_note_returns_true_after_message_is_created(self):
        service = NotificationService()
        fake_chatwoot = SimpleNamespace(
            api_token="token",
            get_or_create_contact=AsyncMock(return_value=123),
            get_or_create_conversation=AsyncMock(return_value=456),
            send_message=AsyncMock(return_value=True),
            add_label=AsyncMock(return_value=True),
        )

        with patch("app.services.notification_service.chatwoot_service", fake_chatwoot):
            ok = await service._crm_private_note(
                "+573001112233",
                "Nota de prueba",
                contact_name="Maria Demo",
                labels=["demo-iniciada"],
            )

        self.assertTrue(ok)
        fake_chatwoot.add_label.assert_awaited_once_with(456, ["demo-iniciada"])


if __name__ == "__main__":
    unittest.main()
