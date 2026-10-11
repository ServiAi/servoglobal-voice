r"""Real PostgreSQL races for the public Voice Experience runtime.

Run only against a dedicated disposable database:

    $env:VOICE_RUNTIME_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_voice_runtime_test"
    .\.venv\Scripts\python.exe -m unittest test_voice_runtime_postgres -v
"""

import asyncio
import hashlib
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
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

from _evaluation_test_seed import seed_voice_technical_health
import app.models  # noqa: F401  (register every ORM table before create_all)
from app.core.config import settings as app_settings
from app.db.base import Base
from app.modules.identity.public import VOICE_RUNTIME_V2
from app.modules.voice.infrastructure.livekit_runtime import RuntimeDispatchResult
from app.modules.voice.infrastructure.models import VoiceSession
from app.modules.billing.infrastructure.models import TenantBillingPlan
from app.modules.crm.infrastructure.models import CrmVoiceCall
from app.modules.identity.infrastructure.models import Tenant
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.models.integrations import TenantVoiceAgentConfig, TenantVoiceProviderConfig
from app.modules.identity.infrastructure.models import TenantFeatureGrant
from app.modules.voice_experiences.infrastructure.context_models import TenantVoiceContextSchema
from app.modules.voice_experiences.infrastructure.experience_models import TenantVoiceExperience, TenantVoiceExperienceVersion
from app.modules.voice_experiences.infrastructure.submission_models import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceRuntimeCall,
)
from app.modules.voice_experiences.domain.errors import PublicCallFailure
from app.services.secret_manager_service import SecretManager


class _SlowLiveKit:
    """LiveKit dispatch double: slow enough that concurrent launches overlap."""

    def __init__(self) -> None:
        self.dispatches: list[str] = []

    async def dispatch(self, session_id: str):
        await asyncio.sleep(0.3)
        self.dispatches.append(session_id)
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

    async def close_session_room(self, session_id: str) -> None: ...


def _livekit_settings():
    stack = ExitStack()
    for name, value in (
        ("LIVEKIT_URL", "wss://livekit.example"),
        ("LIVEKIT_API_KEY", "test-key"),
        ("LIVEKIT_API_SECRET", "s" * 32),
    ):
        stack.enter_context(patch.object(app_settings, name, value))
    return stack


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
        with self.SessionLocal() as db:
            seed_voice_technical_health(db)

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
            canonical_agent = TenantAgent(
                tenant_id=tenant.id,
                name="Runtime Agent",
                status="active",
            )
            db.add(canonical_agent)
            db.flush()
            canonical_version = TenantAgentVersion(
                agent_id=canonical_agent.id,
                tenant_id=tenant.id,
                version=1,
                status="published",
                language="es",
                timezone="America/Bogota",
                identity_json={"name": "Runtime Agent"},
                instructions_json={"system_prompt": "runtime test"},
                behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
                voice_agent_config_id=agent.id,
                published_at=now,
            )
            db.add(canonical_version)
            db.flush()
            canonical_agent.published_version_id = canonical_version.id
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
                agent_id=canonical_agent.id,
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
                agent_id=canonical_agent.id,
                agent_version_id=canonical_version.id,
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

    def _canonical_launch_service(self, backend):
        from app.modules.voice_experiences.application.public_webrtc_service import PublicWebRTCService
        from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

        with self.SessionLocal() as db:
            db.add(
                TenantFeatureGrant(
                    tenant_id=db.scalars(select(Tenant.id)).first(),
                    feature_key=VOICE_RUNTIME_V2,
                    enabled=True,
                    limits_json={},
                )
            )
            db.commit()
        return PublicWebRTCService(
            session_factory=self.SessionLocal,
            runtime_factory=lambda db: VoiceRuntimeAdapter(db, runtime_backend=backend),
        )

    def _concurrent_launches(self, service, seeded):
        barrier = Barrier(2)

        def launch():
            barrier.wait()
            try:
                join = asyncio.run(service.launch(seeded["slug"], seeded["token"]))
                return ("ok", join.server_url)
            except PublicCallFailure as exc:
                return ("failure", exc.code)

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda _: launch(), range(2)))

    def _assert_one_canonical_launch(self, backend, seeded) -> None:
        with self.SessionLocal() as db:
            sessions = db.scalars(select(VoiceSession)).all()
            runtimes = db.scalars(select(TenantVoiceRuntimeCall)).all()
            self.assertEqual((len(sessions), len(runtimes), db.query(CrmVoiceCall).count()), (1, 1, 1))
            self.assertEqual(runtimes[0].voice_session_id, sessions[0].id)
            self.assertEqual(runtimes[0].launch_runtime, 'canonical_voice_session')
            self.assertEqual(sessions[0].crm_voice_call_id, runtimes[0].crm_voice_call_id)
            self.assertEqual(sessions[0].status, "dispatched")
            self.assertEqual(db.get(TenantVoiceContextSession, seeded["context_id"]).status, "consumed")
        self.assertEqual(backend.dispatches, [sessions[0].id])

    def test_simultaneous_public_webrtc_launch_creates_one_ledger_crm_call_session_and_room(self) -> None:
        seeded = self._seed_context()
        backend = _SlowLiveKit()
        service = self._canonical_launch_service(backend)

        with _livekit_settings():
            outcomes = self._concurrent_launches(service, seeded)

        self.assertEqual([kind for kind, _ in outcomes], ["ok", "ok"], outcomes)
        self._assert_one_canonical_launch(backend, seeded)

    def test_concurrent_recovery_of_an_already_claimed_launch_converges_on_one_session(self) -> None:
        seeded = self._seed_context()
        backend = _SlowLiveKit()
        service = self._canonical_launch_service(backend)
        context, _ = service._resolve_session_and_runtime(seeded["slug"], seeded["token"])
        service._claim(seeded["slug"], context.id, service._precheck(context).provider)  # crash right after the claim

        with _livekit_settings():
            outcomes = self._concurrent_launches(service, seeded)

        self.assertEqual([kind for kind, _ in outcomes], ["ok", "ok"], outcomes)
        self._assert_one_canonical_launch(backend, seeded)

    def test_two_workers_placing_the_same_callback_make_one_session_one_dial_one_call(self) -> None:
        """The CrmVoiceCall is the serialized claim: of two concurrent workers exactly one places
        the call; the other finds nothing to claim (never a second session, room or SIP leg)."""
        from threading import Lock

        from app.modules.telephony.infrastructure.livekit_sip import LiveKitSipDialResult
        from app.modules.telephony.infrastructure.models import TenantSipRoute
        from app.modules.telephony.public import TelephonyFacade
        from app.modules.telephony.wiring import default_telephony_ports
        from app.modules.voice_experiences.application.callback_worker import CallbackWorker
        from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

        seeded = self._seed_context()
        session_factory = self.SessionLocal
        with session_factory() as db:
            provider_id = db.scalars(select(TenantVoiceProviderConfig.id)).first()
            route = TenantSipRoute(
                tenant_id=seeded["tenant_id"], provider_config_id=provider_id, status="active",
                pbx_host="pbx.example.com", pbx_port=5060, sip_username=f"u{uuid4().hex[:8]}",
                sip_password_encrypted=SecretManager().encrypt_secret("pw"), caller_id="+573001112233",
                default_country="CO", allowed_countries_json=["CO"], max_concurrent_calls=5,
                provision_status="active", desired_revision=1, applied_revision=1,
                livekit_outbound_trunk_id="ST_pg", livekit_provision_status="active",
                livekit_provisioned_at=datetime.now(UTC),
            )
            db.add(route)
            db.add(TenantFeatureGrant(tenant_id=seeded["tenant_id"], feature_key=VOICE_RUNTIME_V2, enabled=True, limits_json={}))
            db.flush()
            call = CrmVoiceCall(
                tenant_id=seeded["tenant_id"], source_submission_id=seeded["submission_id"], sip_route_id=route.id,
                provider="livekit_sip", origin="voice_experience_callback", direction="outbound",
                status="requested", to_phone="+573001112233", from_number="+573001112233",
            )
            db.add(call)
            db.commit()
            call_id = call.id

        lock, state = Lock(), {"dispatches": 0, "dials": 0}

        class Backend:
            async def dispatch(self, session_id: str):
                await asyncio.sleep(0.2)
                with session_factory() as db:
                    row = db.get(VoiceSession, session_id)
                    row.runtime_ready_at = datetime.now(UTC)
                    db.commit()
                with lock:
                    state["dispatches"] += 1
                return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

            async def close_session_room(self, session_id: str) -> None: ...

        class Sip:
            async def dial(self, **kwargs):
                with lock:
                    state["dials"] += 1
                return LiveKitSipDialResult(
                    participant_id="PA", participant_identity=kwargs["participant_identity"],
                    room_name=kwargs["room_name"], sip_call_id="SC_pg",
                )


        def worker() -> CallbackWorker:
            backend = Backend()
            return CallbackWorker(
                session_factory,
                runtime_factory=lambda db: VoiceRuntimeAdapter(db, runtime_backend=backend),
                telephony_factory=lambda db: TelephonyFacade(
                    db, ports=default_telephony_ports(db, sip_transport=Sip(), runtime_backend=backend)
                ),
            )

        barrier = Barrier(2)

        def run() -> bool:
            barrier.wait()
            return asyncio.run(worker().process_once())

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: run(), range(2)))

        with session_factory() as db:
            sessions = db.scalars(select(VoiceSession)).all()
            calls = db.scalars(select(CrmVoiceCall)).all()
            self.assertEqual((len(sessions), len(calls)), (1, 1))
            self.assertEqual(calls[0].id, call_id)
            self.assertEqual(sessions[0].crm_voice_call_id, call_id)
            self.assertEqual(calls[0].status, "answered")
        self.assertEqual(state, {"dispatches": 1, "dials": 1})

    def test_a_callback_whose_submission_was_deleted_is_failed_closed_by_the_worker(self) -> None:
        """PostgreSQL applies ON DELETE SET NULL for real: the callback must stay recognizable by its
        origin and be failed (not left requested forever, not placed, not handed to a provider)."""
        from sqlalchemy import text

        from app.modules.telephony.infrastructure.models import TenantSipRoute
        from app.modules.voice_experiences.application.callback_worker import CallbackWorker
        from app.modules.voice_experiences.infrastructure.voice_runtime_adapter import VoiceRuntimeAdapter

        seeded = self._seed_context()
        with self.SessionLocal() as db:
            provider_id = db.scalars(select(TenantVoiceProviderConfig.id)).first()
            route = TenantSipRoute(
                tenant_id=seeded["tenant_id"], provider_config_id=provider_id, status="active",
                pbx_host="pbx.example.com", pbx_port=5060, sip_username=f"u{uuid4().hex[:8]}",
                sip_password_encrypted=SecretManager().encrypt_secret("pw"), caller_id="+573001112233",
                default_country="CO", allowed_countries_json=["CO"], max_concurrent_calls=1,
                provision_status="active", desired_revision=1, applied_revision=1,
                livekit_outbound_trunk_id="ST_pg_del", livekit_provision_status="active",
                livekit_provisioned_at=datetime.now(UTC),
            )
            db.add(route)
            db.flush()
            db.add(VoiceSession(  # the route's only channel is taken: lost provenance must still be processed
                tenant_id=seeded["tenant_id"], channel="sip", direction="outbound", purpose="production",
                runtime_engine="livekit", pipeline_type="realtime", provider="ultravox", status="connected",
                sip_route_id=route.id,
            ))
            crm_call = CrmVoiceCall(
                tenant_id=seeded["tenant_id"], source_submission_id=seeded["submission_id"], sip_route_id=route.id,
                provider="livekit_sip", origin="voice_experience_callback", direction="outbound", status="requested",
                to_phone="+573001112233", from_number="+573001112233",
            )
            other = CrmVoiceCall(  # a CRM-initiated outbound call on the same provider: never ours
                tenant_id=seeded["tenant_id"], sip_route_id=route.id, provider="livekit_sip", origin="crm_outbound",
                direction="outbound", status="requested", to_phone="+573009999999", from_number="+573001112233",
            )
            db.add_all([crm_call, other])
            db.commit()
            call_id, other_id = crm_call.id, other.id
        with self.engine.begin() as connection:  # delete the submission for real
            connection.execute(text("DELETE FROM tenant_voice_runtime_calls"))
            connection.execute(text("DELETE FROM tenant_voice_context_sessions"))
            connection.execute(text("DELETE FROM tenant_voice_experience_submission_values"))
            connection.execute(text("DELETE FROM tenant_voice_experience_submissions"))


        worker = CallbackWorker(
            self.SessionLocal,
            runtime_factory=lambda db: VoiceRuntimeAdapter(db),
        )
        asyncio.run(worker.process_once())

        with self.SessionLocal() as db:
            call, other_call = db.get(CrmVoiceCall, call_id), db.get(CrmVoiceCall, other_id)
            self.assertEqual((call.source_submission_id, call.origin), (None, "voice_experience_callback"))
            self.assertEqual((call.status, call.error_message), ("failed", "callback_provenance_unavailable"))
            self.assertEqual((other_call.status, other_call.error_message), ("requested", None))
            self.assertEqual(db.query(VoiceSession).count(), 1)  # only the blocker's own session

    def test_agent_publish_and_experience_publish_serialize_on_the_agent_row(self) -> None:
        from threading import Thread

        from app.modules.agents.application.ports import AgentPorts
        from app.modules.agents.application.service import AgentService
        from app.modules.voice_legacy.public import VoiceLegacyFacade
        from app.modules.voice_experiences.application.experience_service import VoiceExperienceService

        class _Ok:
            def validate_voice(self, *args, **kwargs) -> None: ...
            def is_configured(self, *args, **kwargs) -> bool:
                return True

        seeded = self._seed_context()
        tenant_id = seeded["tenant_id"]
        with self.SessionLocal() as db:
            db.add(TenantFeatureGrant(tenant_id=tenant_id, feature_key="agent_builder_v2", enabled=True, limits_json={}))
            experience = db.get(TenantVoiceExperience, seeded["experience_id"])
            experience.call_settings_json = {"mode": "webrtc"}
            agent_id = experience.agent_id
            v1 = db.get(TenantVoiceExperienceVersion, seeded["version_id"]).agent_version_id
            draft = TenantAgentVersion(
                agent_id=agent_id,
                tenant_id=tenant_id,
                version=2,
                status="draft",
                language="es",
                timezone="America/Bogota",
                identity_json={"name": "Runtime Agent"},
                instructions_json={"system_prompt": "runtime test v2"},
                behavior_json={},
                runtime_binding_json={"pipeline_type": "realtime", "realtime": {"provider": "ultravox"}},
                voice_agent_config_id=seeded["agent_id"],
            )
            db.add(draft)
            db.flush()
            db.get(TenantAgent, agent_id).draft_version_id = draft.id
            db.commit()
            v2 = draft.id
        with self.SessionLocal() as db:
            VoiceExperienceService(db).unpublish_experience(tenant_id, seeded["experience_id"])

        errors: list[BaseException] = []

        def agent_publish() -> None:
            try:
                with self.SessionLocal() as db:
                    ok = _Ok()
                    ports = AgentPorts(voice_provider=ok, legacy_voice=VoiceLegacyFacade(db), integrations=ok, voice_sessions=ok)
                    AgentService(db, ports).publish(tenant_id, agent_id, None)
            except BaseException as exc:  # noqa: BLE001 - surfaced by the assertions below
                errors.append(exc)

        def experience_publish() -> None:
            try:
                with self.SessionLocal() as db:
                    VoiceExperienceService(db).publish_experience(tenant_id, seeded["experience_id"], None)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        with self.SessionLocal() as holder:
            holder.execute(select(TenantAgent).where(TenantAgent.id == agent_id).with_for_update()).scalar_one()
            threads = [Thread(target=agent_publish), Thread(target=experience_publish)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=1.5)
            # Both contend for the same Agent row lock: neither may finish while it is held.
            self.assertTrue(all(thread.is_alive() for thread in threads), repr(errors))
            holder.rollback()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), "deadlock")
        self.assertEqual(errors, [])

        with self.SessionLocal() as db:
            agent = db.get(TenantAgent, agent_id)
            self.assertEqual(agent.published_version_id, v2)
            self.assertEqual(db.get(TenantAgentVersion, v1).status, "superseded")
            bound = db.scalars(
                select(TenantVoiceExperienceVersion).where(
                    TenantVoiceExperienceVersion.experience_id == seeded["experience_id"],
                    TenantVoiceExperienceVersion.version == 2,
                )
            ).one()
            # Whichever won the lock, the Experience pinned one exact, existing version.
            self.assertIn(bound.agent_version_id, {v1, v2})
            pinned = db.get(TenantAgentVersion, bound.agent_version_id)
            self.assertEqual((pinned.agent_id, pinned.tenant_id), (agent_id, tenant_id))
            self.assertEqual(db.get(TenantVoiceExperience, seeded["experience_id"]).published_version_id, bound.id)


if __name__ == "__main__":
    unittest.main()
