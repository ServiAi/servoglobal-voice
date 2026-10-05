r"""Real PostgreSQL races for outbound SIP calls (Telephony + CRM ledger + Voice).

SQLite cannot prove these: they depend on ``SELECT ... FOR UPDATE`` on the
tenant's SIP route and on the unique idempotency constraint. Only the two
external transports (LiveKit SIP, the voice runtime room) are fakes; every
database interaction is real.

Run only against a dedicated disposable database:

    $env:VOICE_RUNTIME_TEST_DATABASE_URL = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai_voice_runtime_test"
    .\.venv\Scripts\python.exe -m unittest test_telephony_postgres -v

Scope: PostgreSQL concurrency with fake transports. It is NOT a real SIP
end-to-end test (no LiveKit, no PBX, no provider credentials).
"""

import asyncio
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

from cryptography.fernet import Fernet

DATABASE_URL = os.environ.get("VOICE_RUNTIME_TEST_DATABASE_URL")
if DATABASE_URL:
    os.environ.setdefault("ULTRAVOX_API_KEY", "test")
    os.environ.setdefault("INTEGRATIONS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    os.environ["DATABASE_URL"] = DATABASE_URL

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import SessionLocal as AppSessionLocal
from app.modules.crm.infrastructure.models import CrmContact, CrmLead, CrmPipelineStage, CrmVoiceCall
from app.modules.identity.infrastructure.models import Tenant
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.telephony.infrastructure.livekit_sip import LiveKitSipDialResult
from app.modules.telephony.infrastructure.models import TenantSipRoute
from app.modules.telephony.public import TelephonyFacade
from app.modules.telephony.wiring import default_telephony_ports
from app.modules.voice.application.session_service import VoiceSessionService
from app.modules.voice.infrastructure.livekit_runtime import RuntimeDispatchResult
from app.modules.voice.infrastructure.models import VoiceSession
from app.schemas.integrations import VoiceCallActionRequest
from app.services.outbound_voice_call_service import OutboundVoiceCallService
from app.modules.identity.application.feature_service import LIVEKIT_SIP_OUTBOUND_V2, VOICE_RUNTIME_V2, TenantFeatureService


class ReadyBackend:
    """Marks the runtime ready the moment it is dispatched."""

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        with AppSessionLocal() as db:
            session = db.get(VoiceSession, session_id)
            session.runtime_ready_at = datetime.now(UTC)
            VoiceSessionService(db).record_event(session, "voice.agent.ready", source="livekit", commit=False)
            db.commit()
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

    async def close_session_room(self, session_id: str) -> None:
        return None


class CountingSip:
    def __init__(self) -> None:
        self.calls = 0

    async def dial(self, **kwargs):
        self.calls += 1
        return LiveKitSipDialResult(
            participant_id="PA_1",
            participant_identity=kwargs["participant_identity"],
            room_name=kwargs["room_name"],
            sip_call_id=f"SC_{self.calls}",
        )


@unittest.skipUnless(
    DATABASE_URL,
    "VOICE_RUNTIME_TEST_DATABASE_URL not set; skipping real PostgreSQL telephony concurrency tests",
)
class TelephonyPostgresConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(DATABASE_URL, pool_pre_ping=True)
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
        self.sip = CountingSip()
        self.backend = ReadyBackend()

    # -- seed -----------------------------------------------------------------

    def _seed(self, *, max_concurrent: int, leads: int) -> dict:
        with self.SessionLocal() as db:
            tenant = Tenant(name="Telephony PG", slug=f"telephony-{uuid4().hex[:8]}")
            db.add(tenant)
            db.flush()
            db.add(
                TenantSipRoute(
                    tenant_id=tenant.id,
                    status="active",
                    pbx_host="pbx.example.com",
                    pbx_port=5060,
                    sip_username=f"sg_{uuid4().hex[:10]}",
                    sip_password_encrypted="not-used-fake-transport",
                    caller_id="+573001112233",
                    default_country="CO",
                    allowed_countries_json=["CO"],
                    max_concurrent_calls=max_concurrent,
                    provision_status="active",
                    desired_revision=1,
                    applied_revision=1,
                    livekit_outbound_trunk_id=f"ST_{uuid4().hex[:8]}",
                    livekit_provision_status="active",
                )
            )
            agent = TenantAgent(tenant_id=tenant.id, name="Outbound agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant.id,
                agent_id=agent.id,
                version=1,
                status="published",
                language="es-CO",
                timezone="America/Bogota",
                identity_json={"name": "Outbound agent"},
                instructions_json={"system_prompt": "Published"},
                behavior_json={},
                runtime_binding_json={
                    "pipeline_type": "realtime",
                    "realtime": {"provider": "ultravox", "model": "fixie-ai/ultravox"},
                },
            )
            db.add(version)
            db.flush()
            agent.status = "active"
            agent.published_version_id = version.id
            stage = CrmPipelineStage(tenant_id=tenant.id, key="new", name="Nuevo", position=1, is_default=True)
            db.add(stage)
            db.flush()
            lead_ids = []
            for index in range(leads):
                contact = CrmContact(
                    tenant_id=tenant.id,
                    name=f"Lead {index}",
                    email=f"lead{index}@example.com",
                    phone="+573001112233",
                )
                db.add(contact)
                db.flush()
                lead = CrmLead(
                    tenant_id=tenant.id, contact_id=contact.id, current_stage_id=stage.id, status="open"
                )
                db.add(lead)
                db.flush()
                lead_ids.append(lead.id)
            features = TenantFeatureService(db)
            for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                features.set_feature(tenant.id, key, True, {}, None)
            db.commit()
            return {"tenant_id": tenant.id, "agent_id": agent.id, "lead_ids": lead_ids}

    # -- helpers --------------------------------------------------------------

    def _place(self, tenant_id: str, lead_id: str, agent_id: str, key: str, barrier: Barrier):
        """One independent request: its own DB session, its own event loop."""
        barrier.wait(timeout=30)
        with self.SessionLocal() as db:
            ports = default_telephony_ports(db, sip_transport=self.sip, runtime_backend=self.backend)
            service = OutboundVoiceCallService(db, telephony=TelephonyFacade(db, ports=ports))
            try:
                return asyncio.run(
                    service.start_call(
                        tenant_id, lead_id, VoiceCallActionRequest(agent_id=agent_id, idempotency_key=key)
                    )
                )
            except ValueError as exc:
                return exc

    def _race(self, tenant_id: str, agent_id: str, requests: list[tuple[str, str]]):
        barrier = Barrier(len(requests))
        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [
                pool.submit(self._place, tenant_id, lead_id, agent_id, key, barrier)
                for lead_id, key in requests
            ]
            return [future.result(timeout=120) for future in futures]

    def _count(self, model, tenant_id: str) -> int:
        with self.SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(model).where(model.tenant_id == tenant_id))

    # -- tests ----------------------------------------------------------------

    def test_same_idempotency_key_in_parallel_creates_one_call_session_and_dial(self) -> None:
        seed = self._seed(max_concurrent=5, leads=1)
        lead_id = seed["lead_ids"][0]
        results = self._race(seed["tenant_id"], seed["agent_id"], [(lead_id, "same-key")] * 4)
        responses = [r for r in results if not isinstance(r, Exception)]
        self.assertTrue(responses, f"no request succeeded: {results!r}")
        self.assertEqual({r.voice_session_id for r in responses}, {responses[0].voice_session_id})
        self.assertEqual(self._count(VoiceSession, seed["tenant_id"]), 1)
        self.assertEqual(self._count(CrmVoiceCall, seed["tenant_id"]), 1)
        self.assertEqual(self.sip.calls, 1)

    def test_max_concurrent_calls_is_enforced_under_parallel_requests(self) -> None:
        seed = self._seed(max_concurrent=1, leads=3)
        requests = [(lead_id, f"key-{index}") for index, lead_id in enumerate(seed["lead_ids"])]
        results = self._race(seed["tenant_id"], seed["agent_id"], requests)
        accepted = [r for r in results if not isinstance(r, Exception)]
        rejected = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(len(rejected), 2, results)
        # Only the accepted call reached the carrier.
        self.assertEqual(self.sip.calls, 1)
        with self.SessionLocal() as db:
            dialled = db.scalar(
                select(func.count())
                .select_from(VoiceSession)
                .where(VoiceSession.tenant_id == seed["tenant_id"], VoiceSession.sip_call_id.is_not(None))
            )
        self.assertEqual(dialled, 1)

    def test_capacity_allows_exactly_max_concurrent_calls(self) -> None:
        seed = self._seed(max_concurrent=2, leads=4)
        requests = [(lead_id, f"key-{index}") for index, lead_id in enumerate(seed["lead_ids"])]
        results = self._race(seed["tenant_id"], seed["agent_id"], requests)
        accepted = [r for r in results if not isinstance(r, Exception)]
        self.assertEqual(len(accepted), 2, results)
        self.assertEqual(self.sip.calls, 2)

    def test_route_row_lock_serialises_concurrent_dials(self) -> None:
        """A second transaction asking for the route ``FOR UPDATE`` waits until
        the first one releases it."""
        seed = self._seed(max_concurrent=1, leads=1)
        from app.modules.telephony.application.route_service import SipRouteService

        first = self.SessionLocal()
        try:
            SipRouteService(first).get_active_route(seed["tenant_id"], for_update=True, require_livekit=True)
            with self.SessionLocal() as second:
                second.execute(__import__("sqlalchemy").text("SET LOCAL lock_timeout = '300ms'"))
                with self.assertRaises(Exception) as ctx:
                    SipRouteService(second).get_active_route(
                        seed["tenant_id"], for_update=True, require_livekit=True
                    )
                self.assertIn("lock", str(ctx.exception).lower())
        finally:
            first.rollback()
            first.close()
        # Released: the lock is obtainable again.
        with self.SessionLocal() as third:
            self.assertIsNotNone(
                SipRouteService(third).get_active_route(seed["tenant_id"], for_update=True, require_livekit=True)
            )


if __name__ == "__main__":
    unittest.main()
