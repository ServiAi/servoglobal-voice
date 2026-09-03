from __future__ import annotations

from unittest.mock import AsyncMock, patch

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.schemas.integrations import ChatwootConfigRequest
from app.services.chatwoot_config_service import ChatwootConfigService


class ChatwootResourcesTests(Integration2ATestCase):
    def setUp(self):
        super().setUp()
        with SessionLocal() as db:
            ChatwootConfigService(db).upsert_config(
                self.tenant.id,
                ChatwootConfigRequest(
                    base_url="https://crm.serviglobal-ia.com",
                    account_id=17,
                    status="active",
                    api_token="cw_secret_token_1234567890",
                ),
            )
        self._old_backend_url = settings.BACKEND_PUBLIC_BASE_URL
        settings.BACKEND_PUBLIC_BASE_URL = "https://api.serviglobal-ia.com"

    def tearDown(self):
        settings.BACKEND_PUBLIC_BASE_URL = self._old_backend_url
        super().tearDown()

    def test_create_inbox(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.create_inbox",
            new_callable=AsyncMock,
            return_value={"id": 42, "name": "Soporte", "channel_type": "Channel::Api"},
        ) as create_inbox:
            response = self.client.post("/api/v1/integrations/chatwoot/inboxes", json={"name": "Soporte"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"id": 42, "name": "Soporte", "channel_type": "Channel::Api"})
        create_inbox.assert_awaited_once()
        self.assertIn("api/v1/webhooks/chatwoot/", create_inbox.call_args.kwargs["webhook_url"])

    def test_create_inbox_requires_backend_public_base_url(self):
        settings.BACKEND_PUBLIC_BASE_URL = ""
        response = self.client.post("/api/v1/integrations/chatwoot/inboxes", json={"name": "Soporte"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("BACKEND_PUBLIC_BASE_URL", response.json()["detail"])

    def test_list_and_create_teams(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.list_teams",
            new_callable=AsyncMock,
            return_value=[{"id": 1, "name": "Comercial"}],
        ):
            list_response = self.client.get("/api/v1/integrations/chatwoot/teams")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json(), [{"id": 1, "name": "Comercial"}])

        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.create_team",
            new_callable=AsyncMock,
            return_value={"id": 2, "name": "Soporte VIP", "description": "Clientes prioritarios"},
        ) as create_team:
            create_response = self.client.post(
                "/api/v1/integrations/chatwoot/teams",
                json={"name": "Soporte VIP", "description": "Clientes prioritarios"},
            )
        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json(), {"id": 2, "name": "Soporte VIP"})
        create_team.assert_awaited_once_with(name="Soporte VIP", description="Clientes prioritarios")

    def test_list_and_invite_agents(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.list_agents",
            new_callable=AsyncMock,
            return_value=[{"id": 9, "name": "Ana", "email": "ana@example.com", "role": "agent", "confirmed": True}],
        ):
            list_response = self.client.get("/api/v1/integrations/chatwoot/agents")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            list_response.json(),
            [{"id": 9, "name": "Ana", "email": "ana@example.com", "role": "agent", "confirmed": True}],
        )

        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.invite_agent",
            new_callable=AsyncMock,
            return_value={"id": 10, "name": "Luis", "email": "luis@example.com", "role": "agent", "confirmed": False},
        ) as invite_agent:
            invite_response = self.client.post(
                "/api/v1/integrations/chatwoot/agents",
                json={"name": "Luis", "email": "luis@example.com", "role": "agent"},
            )
        self.assertEqual(invite_response.status_code, 200)
        self.assertEqual(invite_response.json()["confirmed"], False)
        invite_agent.assert_awaited_once_with(name="Luis", email="luis@example.com", role="agent")

    def test_create_resources_require_active_chatwoot_config(self):
        with SessionLocal() as db:
            ChatwootConfigService(db).disconnect(self.tenant.id)

        response = self.client.post("/api/v1/integrations/chatwoot/inboxes", json={"name": "Soporte"})
        self.assertEqual(response.status_code, 422)

    def test_update_inbox_renames_it(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.update_inbox",
            new_callable=AsyncMock,
            return_value={"id": 42, "name": "Nuevo nombre", "channel_type": "Channel::Api"},
        ) as update_inbox:
            response = self.client.patch(
                "/api/v1/integrations/chatwoot/inboxes/42", json={"name": "Nuevo nombre"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Nuevo nombre")
        update_inbox.assert_awaited_once_with(42, name="Nuevo nombre")

    def test_update_and_delete_team(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.update_team",
            new_callable=AsyncMock,
            return_value={"id": 2, "name": "Renombrado"},
        ) as update_team:
            update_response = self.client.patch(
                "/api/v1/integrations/chatwoot/teams/2", json={"name": "Renombrado"}
            )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json(), {"id": 2, "name": "Renombrado"})
        update_team.assert_awaited_once_with(2, name="Renombrado", description=None)

        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.delete_team", new_callable=AsyncMock
        ) as delete_team:
            delete_response = self.client.delete("/api/v1/integrations/chatwoot/teams/2")
        self.assertEqual(delete_response.status_code, 204)
        delete_team.assert_awaited_once_with(2)

    def test_update_and_delete_agent(self):
        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.update_agent",
            new_callable=AsyncMock,
            return_value={"id": 9, "name": "Ana Maria", "email": "ana@example.com", "role": "administrator", "confirmed": True},
        ) as update_agent:
            update_response = self.client.patch(
                "/api/v1/integrations/chatwoot/agents/9", json={"name": "Ana Maria", "role": "administrator"}
            )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["role"], "administrator")
        update_agent.assert_awaited_once_with(9, name="Ana Maria", role="administrator")

        with patch(
            "app.services.chatwoot_config_service.ChatwootClient.delete_agent", new_callable=AsyncMock
        ) as delete_agent:
            delete_response = self.client.delete("/api/v1/integrations/chatwoot/agents/9")
        self.assertEqual(delete_response.status_code, 204)
        delete_agent.assert_awaited_once_with(9)


if __name__ == "__main__":
    import unittest

    unittest.main()
