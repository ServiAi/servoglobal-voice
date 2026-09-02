from __future__ import annotations

from sqlalchemy import select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.integrations import TenantChatwootConfig, TenantIntegrationEvent
from app.services.chatwoot_client import ChatwootClient, ChatwootClientError
from app.services.chatwoot_platform_client import ChatwootPlatformError


class ChatwootConfigServiceTests(Integration2ATestCase):
    def _payload(self, token: str | None = "cw_secret_token_1234567890"):
        return {
            "base_url": "https://crm.serviglobal-ia.com",
            "account_id": 17,
            "default_inbox_id": 35,
            "status": "active",
            "api_token": token,
        }

    def test_chatwoot_config_encrypts_token_and_does_not_expose_it(self):
        response = self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_secret"])
        self.assertNotIn("cw_secret_token", response.text)
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
            event = db.scalar(select(TenantIntegrationEvent).where(TenantIntegrationEvent.provider == "chatwoot"))
        self.assertIsNotNone(config)
        self.assertNotIn("cw_secret_token", config.api_token_encrypted)
        self.assertIsNotNone(event)
        self.assertTrue(config.webhook_key)

    def test_chatwoot_config_requires_token_only_first_time_and_preserves_existing(self):
        first = self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())
        self.assertEqual(first.status_code, 200)
        with SessionLocal() as db:
            before = db.scalar(
                select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id)
            ).api_token_encrypted
            webhook_key_before = db.scalar(
                select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id)
            ).webhook_key

        second_payload = self._payload(token=None)
        second_payload["default_inbox_id"] = 99
        second = self.client.post("/api/v1/integrations/chatwoot/config", json=second_payload)

        self.assertEqual(second.status_code, 200)
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.api_token_encrypted, before)
        self.assertEqual(config.default_inbox_id, 99)
        self.assertEqual(config.webhook_key, webhook_key_before)

    def test_chatwoot_config_without_initial_token_returns_422(self):
        response = self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload(token=None))

        self.assertEqual(response.status_code, 422)

    def test_chatwoot_webhook_key_is_unique_per_tenant(self):
        self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())
        other_tenant, other_user = self._seed_tenant_user(slug="tenant-b", email="admin-b@example.com")

        def override_for_other():
            with SessionLocal() as db:
                from app.models.identity import TenantMembership
                from app.api.auth.deps import AuthContext

                tenant = db.get(type(self.tenant), other_tenant.id)
                user = db.get(type(self.user), other_user.id)
                membership = db.scalar(
                    select(TenantMembership).where(
                        TenantMembership.tenant_id == other_tenant.id,
                        TenantMembership.user_id == other_user.id,
                    )
                )
                return AuthContext(user=user, tenant=tenant, membership=membership)

        from app.api.auth.deps import get_current_auth_context
        from app.main import app

        app.dependency_overrides[get_current_auth_context] = override_for_other
        response = self.client.post(
            "/api/v1/integrations/chatwoot/config",
            json=self._payload(token="other_secret_token_98765"),
        )
        self.assertEqual(response.status_code, 200)

        with SessionLocal() as db:
            configs = list(db.scalars(select(TenantChatwootConfig)))
        self.assertEqual(len(configs), 2)
        self.assertNotEqual(configs[0].webhook_key, configs[1].webhook_key)

    def test_chatwoot_test_connection_marks_health_with_mock(self):
        self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())

        class _Client(ChatwootClient):
            def get_account_profile(self):
                return {"id": 17, "name": "Clinica ABC"}

        import app.services.chatwoot_config_service as module

        original = module.ChatwootClient
        module.ChatwootClient = _Client
        try:
            with SessionLocal() as db:
                from app.services.chatwoot_config_service import ChatwootConfigService

                result = ChatwootConfigService(db).test_connection(self.tenant.id)
        finally:
            module.ChatwootClient = original

        self.assertEqual(result.status, "success")
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertIsNotNone(config.last_health_check_at)
        self.assertIsNone(config.last_error_message)
        self.assertEqual(config.account_name, "Clinica ABC")

    def test_chatwoot_test_connection_marks_error_on_failure(self):
        self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())

        class _FailingClient(ChatwootClient):
            def get_account_profile(self):
                raise ChatwootClientError("Chatwoot request failed")

        import app.services.chatwoot_config_service as module

        original = module.ChatwootClient
        module.ChatwootClient = _FailingClient
        try:
            with SessionLocal() as db:
                from app.services.chatwoot_config_service import ChatwootConfigService

                result = ChatwootConfigService(db).test_connection(self.tenant.id)
        finally:
            module.ChatwootClient = original

        self.assertEqual(result.status, "failed")
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertIsNotNone(config.last_error_message)

    def test_chatwoot_provision_requires_platform_token(self):
        original_token = settings.CHATWOOT_PLATFORM_API_TOKEN
        settings.CHATWOOT_PLATFORM_API_TOKEN = ""
        try:
            response = self.client.post("/api/v1/integrations/chatwoot/provision", json={})
        finally:
            settings.CHATWOOT_PLATFORM_API_TOKEN = original_token
        self.assertEqual(response.status_code, 422)
        self.assertIn("CHATWOOT_PLATFORM_API_TOKEN", response.json()["detail"])

    def test_chatwoot_provision_managed_creates_active_config(self):
        class _FakePlatformClient:
            def __init__(self, base_url, token):
                pass

            def create_account(self, *, name):
                return {"id": 42, "name": name}

            def create_user(self, *, name, email, password):
                return {"id": 5, "access_token": "user_access_token_123"}

            def link_account_user(self, *, account_id, user_id, role="administrator"):
                return {"account_id": account_id, "user_id": user_id, "role": role}

            def create_api_inbox(self, *, account_id, user_token, name, webhook_url):
                return {"id": 99, "name": name}

            def create_account_webhook(self, *, account_id, user_token, url):
                return {"payload": {"webhook": {"id": 1, "url": url}}}

        import app.services.chatwoot_config_service as module

        original_client = module.ChatwootPlatformClient
        original_token = settings.CHATWOOT_PLATFORM_API_TOKEN
        original_backend_url = settings.BACKEND_PUBLIC_BASE_URL
        module.ChatwootPlatformClient = _FakePlatformClient
        settings.CHATWOOT_PLATFORM_API_TOKEN = "platform_token_test"
        settings.BACKEND_PUBLIC_BASE_URL = "https://api.serviglobal-ia.com"
        try:
            response = self.client.post(
                "/api/v1/integrations/chatwoot/provision", json={"account_name": "Clinica ABC"}
            )
        finally:
            module.ChatwootPlatformClient = original_client
            settings.CHATWOOT_PLATFORM_API_TOKEN = original_token
            settings.BACKEND_PUBLIC_BASE_URL = original_backend_url

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["mode"], "managed")
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["account_id"], 42)
        self.assertEqual(body["default_inbox_id"], 99)
        self.assertTrue(body["has_secret"])

        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.mode, "managed")
        self.assertNotIn("user_access_token_123", config.api_token_encrypted)

    def test_chatwoot_provision_fails_without_persisting_when_account_creation_fails(self):
        class _FailingAtAccountPlatformClient:
            def __init__(self, base_url, token):
                pass

            def create_account(self, *, name):
                raise ChatwootPlatformError("Chatwoot platform request failed (401)")

        import app.services.chatwoot_config_service as module

        original_client = module.ChatwootPlatformClient
        original_token = settings.CHATWOOT_PLATFORM_API_TOKEN
        original_backend_url = settings.BACKEND_PUBLIC_BASE_URL
        module.ChatwootPlatformClient = _FailingAtAccountPlatformClient
        settings.CHATWOOT_PLATFORM_API_TOKEN = "platform_token_test"
        settings.BACKEND_PUBLIC_BASE_URL = "https://api.serviglobal-ia.com"
        try:
            response = self.client.post(
                "/api/v1/integrations/chatwoot/provision", json={"account_name": "Clinica ABC"}
            )
        finally:
            module.ChatwootPlatformClient = original_client
            settings.CHATWOOT_PLATFORM_API_TOKEN = original_token
            settings.BACKEND_PUBLIC_BASE_URL = original_backend_url

        self.assertEqual(response.status_code, 422)
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertIsNone(config)

    def test_chatwoot_provision_marks_error_but_keeps_account_id_on_later_step_failure(self):
        class _FailingPlatformClient:
            def __init__(self, base_url, token):
                pass

            def create_account(self, *, name):
                return {"id": 42, "name": name}

            def create_user(self, *, name, email, password):
                raise ChatwootPlatformError("Chatwoot platform request failed (401)")

        import app.services.chatwoot_config_service as module

        original_client = module.ChatwootPlatformClient
        original_token = settings.CHATWOOT_PLATFORM_API_TOKEN
        original_backend_url = settings.BACKEND_PUBLIC_BASE_URL
        module.ChatwootPlatformClient = _FailingPlatformClient
        settings.CHATWOOT_PLATFORM_API_TOKEN = "platform_token_test"
        settings.BACKEND_PUBLIC_BASE_URL = "https://api.serviglobal-ia.com"
        try:
            response = self.client.post(
                "/api/v1/integrations/chatwoot/provision", json={"account_name": "Clinica ABC"}
            )
        finally:
            module.ChatwootPlatformClient = original_client
            settings.CHATWOOT_PLATFORM_API_TOKEN = original_token
            settings.BACKEND_PUBLIC_BASE_URL = original_backend_url

        self.assertEqual(response.status_code, 422)
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.mode, "managed")
        self.assertEqual(config.status, "error")
        self.assertEqual(config.account_id, 42)
        self.assertIsNotNone(config.last_error_message)

    def test_chatwoot_disconnect_deactivates_without_deleting_config(self):
        self.client.post("/api/v1/integrations/chatwoot/config", json=self._payload())

        response = self.client.post("/api/v1/integrations/chatwoot/disconnect")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "inactive")
        self.assertTrue(body["has_secret"])
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.status, "inactive")
        self.assertIsNotNone(config.api_token_encrypted)
        self.assertIsNotNone(config.webhook_key)

    def test_chatwoot_disconnect_without_config_returns_422(self):
        response = self.client.post("/api/v1/integrations/chatwoot/disconnect")
        self.assertEqual(response.status_code, 422)

    def test_chatwoot_provision_reactivates_disconnected_managed_config_without_new_account(self):
        class _FakePlatformClient:
            def __init__(self, base_url, token):
                pass

            def create_account(self, *, name):
                raise AssertionError("no deberia crear una Account nueva al reactivar")

        with SessionLocal() as db:
            config = TenantChatwootConfig(
                tenant_id=self.tenant.id,
                provider="chatwoot",
                mode="managed",
                status="inactive",
                base_url="https://crm.serviglobal-ia.com",
                account_id=42,
                account_name="Clinica ABC",
                default_inbox_id=99,
                default_inbox_name="Conversaciones",
                api_token_encrypted="already-encrypted-token",
                webhook_key="existing-webhook-key",
            )
            db.add(config)
            db.commit()

        import app.services.chatwoot_config_service as module

        original_client = module.ChatwootPlatformClient
        module.ChatwootPlatformClient = _FakePlatformClient
        try:
            response = self.client.post("/api/v1/integrations/chatwoot/provision", json={})
        finally:
            module.ChatwootPlatformClient = original_client

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["account_id"], 42)
        self.assertEqual(body["account_name"], "Clinica ABC")
        with SessionLocal() as db:
            config = db.scalar(select(TenantChatwootConfig).where(TenantChatwootConfig.tenant_id == self.tenant.id))
        self.assertEqual(config.status, "active")
        self.assertEqual(config.webhook_key, "existing-webhook-key")


if __name__ == "__main__":
    import unittest

    unittest.main()
