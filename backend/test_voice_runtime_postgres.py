r"""Real PostgreSQL races for the public Voice Experience runtime.

Run only against a dedicated disposable database:

    $env:VOICE_RUNTIME_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_voice_runtime_test"
    .\.venv\Scripts\python.exe -m unittest test_voice_runtime_postgres -v
"""

import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from cryptography.fernet import Fernet

VOICE_RUNTIME_TEST_DATABASE_URL = os.environ.get("VOICE_RUNTIME_TEST_DATABASE_URL")
if VOICE_RUNTIME_TEST_DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ.setdefault("INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ["DATABASE_URL"] = VOICE_RUNTIME_TEST_DATABASE_URL

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.analytics import Call, CallEvent
from app.models.billing import TenantBillingPlan
from app.models.crm import CrmVoiceCall, CrmVoiceCallEvent
from app.models.identity import Tenant
from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.models.tenant_features import TenantFeatureGrant
from app.models.voice_context import TenantVoiceContextSchema
from app.models.voice_experiences import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceRuntimeCall,
)
from app.services.public_voice_call_service import PublicCallFailure, PublicVoiceCallService
from app.services.secret_manager_service import SecretManager
from app.services.voice_experience_runtime_provider import ProviderCallResult
from app.services.voice_runtime_webhook_service import RuntimeWebhookTarget, VoiceRuntimeWebhookService


@unittest.skipUnless(
    VOICE_RUNTIME_TEST_DATABASE_URL,
    "VOICE_RUNTIME_TEST_DATABASE_URL not set; skipping real PostgreSQL concurrency tests",
)
class VoiceRuntimePostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(VOICE_RUNTIME_TEST_DATABASE_URL, pool_pre_ping=True)
        if cls.engine.dialect.name != "postgresql":
            raise unittest.SkipTest("VOICE_RUNTIME_TEST_DATABASE_URL must point to PostgreSQL")
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self) -> None:
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def _seed_context(self) -> dict[str, str]:
        now = datetime.now(UTC)
        token = uuid4().hex + uuid4().hex
        with self.SessionLocal() as db:
            tenant = Tenant(name="Voice Runtime PG", slug=f"voice-runtime-{uuid4().hex[:8]}")
            db.add(tenant)
            db.flush()
            secrets = SecretManager()
            config = TenantVoiceProviderConfig(
                tenant_id=tenant.id,
                provider="ultravox",
                status="active",
                api_key_encrypted=secrets.encrypt_secret("test-api-key"),
                webhook_secret_encrypted=secrets.encrypt_secret("test-webhook-secret"),
            )
            db.add(config)
            db.flush()
            agent = TenantVoiceAgentConfig(
                tenant_id=tenant.id,
                provider_config_id=config.id,
                provider="ultravox",
                provider_agent_id=f"agent-{uuid4().hex[:8]}",
                display_name="Runtime Agent",
                status="active",
            )
            db.add(agent)
            db.flush()
            schema = TenantVoiceContextSchema(
                tenant_id=tenant.id,
                agent_config_id=agent.id,
                schema_key="runtime",
                version=1,
                status="active",
                name="Runtime",
                activated_at=now,
            )
            db.add(schema)
            db.flush()
            experience = TenantVoiceExperience(
                tenant_id=tenant.id,
                agent_config_id=agent.id,
                context_schema_id=schema.id,
                name="Runtime",
                slug=f"runtime-{uuid4().hex[:12]}",
                status="published",
                content_json={},
                theme_json={},
                consent_json={},
                call_settings_json={},
            )
            db.add(experience)
            db.flush()
            version = TenantVoiceExperienceVersion(
                experience_id=experience.id,
                tenant_id=tenant.id,
                version=1,
                agent_config_id=agent.id,
                context_schema_id=schema.id,
                name=experience.name,
                slug=experience.slug,
                default_locale="es",
                content_json={},
                theme_json={},
                consent_json={},
                call_settings_json={},
                published_at=now,
            )
            db.add(version)
            db.flush()
            experience.published_version_id = version.id
            submission = TenantVoiceExperienceSubmission(
                tenant_id=tenant.id,
                experience_id=experience.id,
                experience_version_id=version.id,
                context_schema_id=schema.id,
                version=1,
                locale="es",
                consent_accepted=True,
                consent_accepted_at=now,
            )
            db.add(submission)
            db.flush()
            context = TenantVoiceContextSession(
                tenant_id=tenant.id,
                submission_id=submission.id,
                experience_id=experience.id,
                experience_version_id=version.id,
                context_schema_id=schema.id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                status="active",
                expires_at=now + timedelta(minutes=10),
            )
            db.add_all(
                [
                    context,
                    TenantFeatureGrant(
                        tenant_id=tenant.id,
                        feature_key="voice_experiences",
                        enabled=True,
                        limits_json={"max_experiences": 10, "max_context_fields": 20},
                    ),
                    TenantBillingPlan(
                        tenant_id=tenant.id,
                        plan_key="web_conversion",
                        plan_name="Web Conversion",
                        included_minutes=Decimal("2000"),
                        price_per_minute_usd=Decimal("0.16"),
                        usage_status="normal",
                        billing_period_start=now - timedelta(days=1),
                        billing_period_end=now + timedelta(days=29),
                        alert_thresholds=[80, 90, 100],
                    ),
                ]
            )
            db.commit()
            return {
                "tenant_id": tenant.id,
                "slug": experience.slug,
                "token": token,
                "context_id": context.id,
                "submission_id": submission.id,
                "experience_id": experience.id,
                "version_id": version.id,
                "agent_id": agent.id,
            }

    def _service(self) -> PublicVoiceCallService:
        return PublicVoiceCallService(
            session_factory=self.SessionLocal,
            provider_timeout_seconds=1,
            reserved_lease_seconds=1,
            starting_lease_seconds=1,
        )

    def _seed_reserved_runtime(self, seeded: dict[str, str]) -> str:
        with self.SessionLocal() as db:
            crm = CrmVoiceCall(
                tenant_id=seeded["tenant_id"],
                provider="ultravox",
                provider_agent_id="runtime-agent",
                direction="webrtc",
                status="requested",
            )
            db.add(crm)
            db.flush()
            runtime = TenantVoiceRuntimeCall(
                tenant_id=seeded["tenant_id"],
                context_session_id=seeded["context_id"],
                submission_id=seeded["submission_id"],
                experience_id=seeded["experience_id"],
                experience_version_id=seeded["version_id"],
                agent_config_id=seeded["agent_id"],
                crm_voice_call_id=crm.id,
                provider="ultravox",
                status="reserved",
                created_at=datetime.now(UTC) - timedelta(seconds=10),
            )
            db.add(runtime)
            context = db.get(TenantVoiceContextSession, seeded["context_id"])
            context.status = "consumed"
            context.consumed_at = datetime.now(UTC)
            db.commit()
            return runtime.id

    def _webhook_target(self, db, runtime_id: str) -> RuntimeWebhookTarget:
        runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
        return RuntimeWebhookTarget(db.get(CrmVoiceCall, runtime.crm_voice_call_id), runtime)

    def test_simultaneous_first_launch_creates_one_runtime_crm_call_and_provider_call(self) -> None:
        seeded = self._seed_context()
        barrier = Barrier(2)

        def launch():
            barrier.wait()
            try:
                return self._service().launch(seeded["slug"], seeded["token"]).status
            except PublicCallFailure as exc:
                return exc.code

        with patch(
            "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
            return_value=ProviderCallResult("provider-first", "https://provider.invalid/join/first"),
        ) as create_call, patch(
            "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
            return_value=ProviderCallResult("provider-first", "https://provider.invalid/join/first"),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: launch(), range(2)))

        self.assertTrue(set(outcomes) <= {"ready", "call_already_started"})
        self.assertEqual(create_call.call_count, 1)
        with self.SessionLocal() as db:
            self.assertEqual(db.query(TenantVoiceRuntimeCall).count(), 1)
            self.assertEqual(db.query(CrmVoiceCall).count(), 1)
            self.assertEqual(db.get(TenantVoiceContextSession, seeded["context_id"]).status, "consumed")

    def test_stale_reserved_takeover_has_one_update_returning_winner_and_provider_call(self) -> None:
        runtime_id = self._seed_reserved_runtime(self._seed_context())
        barrier = Barrier(2)

        def recover():
            barrier.wait()
            try:
                return self._service()._recover(runtime_id).status
            except PublicCallFailure as exc:
                return exc.code

        with patch(
            "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.create_webrtc_call",
            return_value=ProviderCallResult("provider-takeover", "https://provider.invalid/join/takeover"),
        ) as create_call, patch(
            "app.services.voice_experience_runtime_provider.VoiceExperienceRuntimeProvider.get_call",
            return_value=ProviderCallResult("provider-takeover", "https://provider.invalid/join/takeover"),
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: recover(), range(2)))

        self.assertTrue(set(outcomes) <= {"ready", "call_already_started"})
        self.assertEqual(create_call.call_count, 1)
        with self.SessionLocal() as db:
            self.assertEqual(db.get(TenantVoiceRuntimeCall, runtime_id).status, "ready")

    def test_concurrent_identical_webhook_has_one_owner_and_one_core_mutation(self) -> None:
        runtime_id = self._seed_reserved_runtime(self._seed_context())
        with self.SessionLocal() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            runtime.status = "ready"
            runtime.provider_call_id = "provider-webhook-race"
            db.get(CrmVoiceCall, runtime.crm_voice_call_id).status = "queued"
            db.commit()
        payload = {"event": "call.joined", "call": {"callId": "provider-webhook-race"}}
        barrier = Barrier(2)

        def process() -> bool:
            with self.SessionLocal() as db:
                target = self._webhook_target(db, runtime_id)
                barrier.wait()
                return VoiceRuntimeWebhookService(db).process("ultravox", payload, target)["processed"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: process(), range(2)))

        self.assertEqual(sorted(results), [False, True])
        with self.SessionLocal() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            self.assertEqual(runtime.status, "connected")
            self.assertEqual(db.get(CrmVoiceCall, runtime.crm_voice_call_id).status, "in_progress")
            self.assertEqual(db.query(CallEvent).count(), 1)
            self.assertEqual(db.query(CrmVoiceCallEvent).count(), 1)
            self.assertEqual(db.query(Call).count(), 1)

    def test_core_webhook_rollback_releases_dedup_for_retry(self) -> None:
        runtime_id = self._seed_reserved_runtime(self._seed_context())
        with self.SessionLocal() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            runtime.status = "ready"
            runtime.provider_call_id = "provider-webhook-retry"
            db.commit()
        payload = {
            "event": "call.ended",
            "call": {"callId": "provider-webhook-retry", "duration": "75s"},
        }
        with self.SessionLocal() as db:
            service = VoiceRuntimeWebhookService(db)
            target = self._webhook_target(db, runtime_id)
            with patch.object(service, "_integer", side_effect=RuntimeError("forced core rollback")):
                with self.assertRaisesRegex(RuntimeError, "forced core rollback"):
                    service.process("ultravox", payload, target)
            self.assertEqual(db.query(CrmVoiceCallEvent).count(), 0)
            self.assertTrue(service.process("ultravox", payload, target)["processed"])

        with self.SessionLocal() as db:
            runtime = db.get(TenantVoiceRuntimeCall, runtime_id)
            self.assertEqual(runtime.status, "ended")
            self.assertEqual(db.query(CallEvent).count(), 1)
            self.assertEqual(db.query(CrmVoiceCallEvent).count(), 1)


if __name__ == "__main__":
    unittest.main()
