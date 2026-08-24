from __future__ import annotations

from cryptography.fernet import Fernet

from _integrations_2a_test_base import Integration2ATestCase
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.integrations import TenantSipRoute, TenantVoiceProviderConfig
from app.services.secret_manager_service import SecretManager


class AsteriskProvisioningApiTests(Integration2ATestCase):
    def setUp(self) -> None:
        self.original_encryption_key = settings.INTEGRATIONS_ENCRYPTION_KEY
        self.original_provisioner_secret = settings.ASTERISK_PROVISIONER_SHARED_SECRET
        settings.INTEGRATIONS_ENCRYPTION_KEY = Fernet.generate_key().decode()
        settings.ASTERISK_PROVISIONER_SHARED_SECRET = "provisioner-test-secret"
        super().setUp()
        secrets = SecretManager()
        with SessionLocal() as db:
            provider = TenantVoiceProviderConfig(
                tenant_id=self.tenant.id, provider="ultravox", status="active"
            )
            db.add(provider)
            db.flush()
            route = TenantSipRoute(
                tenant_id=self.tenant.id,
                provider_config_id=provider.id,
                status="active",
                pbx_host="pbx.example.com",
                pbx_port=5060,
                sip_username="tenant-a",
                sip_password_encrypted=secrets.encrypt_secret("SipPassword2026*+"),
                caller_id="+573001112233",
                default_country="CO",
                allowed_countries_json=["CO"],
                max_concurrent_calls=1,
                provision_status="pending",
                desired_revision=2,
                applied_revision=1,
            )
            db.add(route)
            db.commit()
            self.route_id = route.id

    def tearDown(self) -> None:
        settings.INTEGRATIONS_ENCRYPTION_KEY = self.original_encryption_key
        settings.ASTERISK_PROVISIONER_SHARED_SECRET = self.original_provisioner_secret
        super().tearDown()

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Asterisk-Provisioner-Secret": "provisioner-test-secret"}

    def test_desired_state_requires_dedicated_secret_and_returns_route(self) -> None:
        self.assertEqual(
            self.client.get("/api/v1/internal/asterisk/desired-state").status_code,
            401,
        )
        response = self.client.get(
            "/api/v1/internal/asterisk/desired-state", headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        route = response.json()["routes"][0]
        self.assertEqual(route["route_id"], self.route_id)
        self.assertEqual(route["sip_password"], "SipPassword2026*+")
        self.assertNotIn(self.tenant.id, route["route_key"])

    def test_apply_result_activates_revision_and_ignores_stale_result(self) -> None:
        applied = self.client.post(
            "/api/v1/internal/asterisk/apply-results",
            headers=self.headers,
            json={
                "results": [
                    {"route_id": self.route_id, "revision": 2, "success": True}
                ]
            },
        )
        self.assertEqual(applied.json(), {"accepted": 1, "ignored": 0})
        stale = self.client.post(
            "/api/v1/internal/asterisk/apply-results",
            headers=self.headers,
            json={
                "results": [
                    {
                        "route_id": self.route_id,
                        "revision": 1,
                        "success": False,
                        "error_code": "reload_failed",
                    }
                ]
            },
        )
        self.assertEqual(stale.json(), {"accepted": 0, "ignored": 1})
        with SessionLocal() as db:
            route = db.get(TenantSipRoute, self.route_id)
            self.assertEqual(route.provision_status, "active")
            self.assertEqual(route.applied_revision, 2)
            self.assertIsNone(route.provision_error_code)

