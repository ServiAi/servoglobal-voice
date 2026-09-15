from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select

from _integrations_2a_test_base import Integration2ATestCase, SessionLocal
from app.core.config import settings
from app.models.agents import TenantAgent, TenantAgentVersion
from app.models.crm import CrmVoiceCall
from app.models.integrations import TenantSipRoute
from app.models.voice_sessions import VoiceSession
from app.schemas.integrations import VoiceCallActionRequest
from app.services.livekit_runtime_backend import RuntimeDispatchResult
from app.services.livekit_sip_service import (
    LiveKitSipDialError,
    LiveKitSipDialResult,
    LiveKitSipError,
)
from app.services.outbound_voice_call_service import OutboundVoiceCallService
from app.services.tenant_feature_service import (
    LIVEKIT_SIP_OUTBOUND_V2,
    VOICE_RUNTIME_V2,
    TenantFeatureService,
)
from app.services.voice_session_service import VoiceSessionService
from app.services.voice_sip_route_service import VoiceSipRouteService


class ReadyBackend:
    def __init__(self, order) -> None:
        self.order = order
        self.closed = []

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        self.order.append("dispatch")
        with SessionLocal() as db:
            session = db.get(VoiceSession, session_id)
            session.runtime_ready_at = datetime.now(UTC)
            VoiceSessionService(db).record_event(
                session, "voice.agent.ready", source="livekit", commit=False
            )
            db.commit()
        self.order.append("ready")
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")

    async def close_session_room(self, session_id: str) -> None:
        self.closed.append(session_id)


class NeverReadyBackend(ReadyBackend):
    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        self.order.append("dispatch")
        return RuntimeDispatchResult(f"sg-vs-{session_id}", "dispatch-1")


class FakeSip:
    def __init__(self, order, error=None) -> None:
        self.order = order
        self.error = error
        self.calls = 0
        self.last_kwargs = None

    async def dial(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        self.order.append("dial")
        if self.error:
            raise self.error
        return LiveKitSipDialResult(
            participant_id="PA_1",
            participant_identity=kwargs["participant_identity"],
            room_name=kwargs["room_name"],
            sip_call_id="SC_1",
        )


class FakeTrunkProvisioner:
    def __init__(self, error=None) -> None:
        self.error = error

    async def provision_outbound_trunk(self, **kwargs):
        if self.error:
            raise self.error
        return SimpleNamespace(sip_trunk_id="ST_persisted")


class OutboundVoiceCallServiceTests(Integration2ATestCase):
    def _enable_v2(self) -> None:
        with SessionLocal() as db:
            features = TenantFeatureService(db)
            for key in (VOICE_RUNTIME_V2, LIVEKIT_SIP_OUTBOUND_V2):
                features.set_feature(self.tenant.id, key, True, {}, self.user.id)

    def _configure_route(self) -> str:
        response = self.client.post(
            "/api/v1/integrations/voice/config",
            json={
                "provider": "ultravox",
                "api_key": "tenant-ultravox-key",
                "status": "active",
                "sip_route": {
                    "status": "active",
                    "pbx_host": "pbx.example.com",
                    "pbx_port": 5060,
                    "sip_password": "test-sip-password",
                    "caller_id": "+573001112233",
                    "default_country": "CO",
                    "allowed_countries": ["CO"],
                    "max_concurrent_calls": 1,
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        with SessionLocal() as db:
            route = db.scalar(select(TenantSipRoute).where(TenantSipRoute.tenant_id == self.tenant.id))
            route.applied_revision = route.desired_revision
            route.provision_status = "active"
            route.livekit_outbound_trunk_id = "ST_tenant_a"
            route.livekit_provision_status = "active"
            db.commit()
            return route.id

    def _published_agent(self, tenant_id=None) -> str:
        tenant_id = tenant_id or self.tenant.id
        with SessionLocal() as db:
            agent = TenantAgent(tenant_id=tenant_id, name="Outbound agent", status="draft")
            db.add(agent)
            db.flush()
            version = TenantAgentVersion(
                tenant_id=tenant_id,
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
            db.commit()
            return agent.id

    def _request(self, agent_id: str, key: str = "request-1") -> VoiceCallActionRequest:
        return VoiceCallActionRequest(agent_id=agent_id, idempotency_key=key)

    def test_dispatch_ready_then_dial_and_persist_correlations(self) -> None:
        route_id = self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        order = []
        sip = FakeSip(order)
        backend = ReadyBackend(order)
        with SessionLocal() as db:
            response = asyncio.run(
                OutboundVoiceCallService(db, sip_service=sip, runtime_backend=backend).start_call(
                    self.tenant.id, lead_id, self._request(agent_id)
                )
            )
        self.assertEqual(order, ["dispatch", "ready", "dial"])
        self.assertEqual(response.status, "answered")
        with SessionLocal() as db:
            session = db.get(VoiceSession, response.voice_session_id)
            call = db.get(CrmVoiceCall, response.voice_call_id)
            self.assertEqual(session.channel, "sip")
            self.assertEqual(session.direction, "outbound")
            self.assertEqual(session.crm_voice_call_id, call.id)
            self.assertEqual(session.sip_route_id, route_id)
            self.assertEqual(session.sip_call_id, "SC_1")
            self.assertEqual(call.status, "answered")
            self.assertIsNotNone(call.answered_at)

    def test_idempotent_retry_creates_one_call_session_and_dial(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        order = []
        sip = FakeSip(order)
        backend = ReadyBackend(order)
        with SessionLocal() as db:
            service = OutboundVoiceCallService(db, sip_service=sip, runtime_backend=backend)
            first = asyncio.run(service.start_call(self.tenant.id, lead_id, self._request(agent_id)))
            second = asyncio.run(service.start_call(self.tenant.id, lead_id, self._request(agent_id)))
        self.assertEqual(first.voice_call_id, second.voice_call_id)
        self.assertEqual(sip.calls, 1)
        with SessionLocal() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(VoiceSession)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(CrmVoiceCall)), 1)

    def test_trunk_id_is_persisted_only_after_successful_provisioning(self) -> None:
        route_id = self._configure_route()
        with SessionLocal() as db:
            route = db.get(TenantSipRoute, route_id)
            route.livekit_outbound_trunk_id = None
            route.livekit_provision_status = "disabled"
            db.commit()
            asyncio.run(
                VoiceSipRouteService(db).provision_livekit_outbound(
                    route, FakeTrunkProvisioner()
                )
            )
            self.assertEqual(route.livekit_outbound_trunk_id, "ST_persisted")
            self.assertEqual(route.livekit_provision_status, "active")

    def test_failed_provisioning_does_not_invent_a_trunk_id(self) -> None:
        route_id = self._configure_route()
        with SessionLocal() as db:
            route = db.get(TenantSipRoute, route_id)
            route.livekit_outbound_trunk_id = None
            route.livekit_provision_status = "disabled"
            db.commit()
            with self.assertRaisesRegex(ValueError, "provisioning failed"):
                asyncio.run(
                    VoiceSipRouteService(db).provision_livekit_outbound(
                        route,
                        FakeTrunkProvisioner(LiveKitSipError("livekit_sip_unavailable")),
                    )
                )
            self.assertIsNone(route.livekit_outbound_trunk_id)
            self.assertEqual(route.livekit_provision_status, "failed")

    def test_busy_maps_call_and_cleans_room(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        order = []
        backend = ReadyBackend(order)
        sip = FakeSip(order, LiveKitSipDialError("busy", 486))
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "livekit_sip_busy"):
                asyncio.run(
                    OutboundVoiceCallService(db, sip_service=sip, runtime_backend=backend).start_call(
                        self.tenant.id, lead_id, self._request(agent_id)
                    )
                )
        with SessionLocal() as db:
            call = db.scalar(select(CrmVoiceCall))
            session = db.scalar(select(VoiceSession))
            self.assertEqual(call.status, "busy")
            self.assertEqual(session.status, "failed")
            self.assertEqual(backend.closed, [session.id])

    def test_rejected_no_answer_and_provider_failure_map_to_telephony(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead(email="sip-statuses@example.com")
        for index, (sip_code, expected) in enumerate(
            ((603, "rejected"), (408, "no_answer"), (500, "failed")), start=1
        ):
            with self.subTest(sip_code=sip_code):
                sip = FakeSip([], LiveKitSipDialError(expected, sip_code))
                with SessionLocal() as db:
                    with self.assertRaises(ValueError):
                        asyncio.run(
                            OutboundVoiceCallService(
                                db, sip_service=sip, runtime_backend=ReadyBackend([])
                            ).start_call(
                                self.tenant.id,
                                lead_id,
                                self._request(agent_id, f"status-{index}"),
                            )
                        )
                with SessionLocal() as db:
                    call = db.scalar(
                        select(CrmVoiceCall).where(
                            CrmVoiceCall.lead_id == lead_id,
                            CrmVoiceCall.status == expected,
                        )
                    )
                    self.assertEqual(call.status, expected)

    def test_runtime_not_ready_never_dials(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        order = []
        sip = FakeSip(order)
        backend = NeverReadyBackend(order)
        with patch.object(settings, "LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS", 0.01):
            with SessionLocal() as db:
                with self.assertRaisesRegex(ValueError, "did not become ready"):
                    asyncio.run(
                        OutboundVoiceCallService(db, sip_service=sip, runtime_backend=backend).start_call(
                            self.tenant.id, lead_id, self._request(agent_id)
                        )
                    )
        self.assertEqual(sip.calls, 0)

    def test_inactive_route_is_rejected_before_dispatch(self) -> None:
        route_id = self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        with SessionLocal() as db:
            db.get(TenantSipRoute, route_id).status = "inactive"
            db.commit()
        backend = ReadyBackend([])
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "inactiva"):
                asyncio.run(
                    OutboundVoiceCallService(
                        db, sip_service=FakeSip([]), runtime_backend=backend
                    ).start_call(self.tenant.id, lead_id, self._request(agent_id))
                )
        self.assertEqual(backend.order, [])

    def test_capacity_exceeded_never_dials(self) -> None:
        route_id = self._configure_route()
        agent_id = self._published_agent()
        lead_id, contact_id = self.seed_lead()
        with SessionLocal() as db:
            db.add(
                CrmVoiceCall(
                    tenant_id=self.tenant.id,
                    lead_id=lead_id,
                    contact_id=contact_id,
                    sip_route_id=route_id,
                    provider="livekit_sip",
                    direction="outbound",
                    status="queued",
                )
            )
            db.commit()
        sip = FakeSip([])
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "capacity exceeded"):
                asyncio.run(
                    OutboundVoiceCallService(
                        db, sip_service=sip, runtime_backend=ReadyBackend([])
                    ).start_call(self.tenant.id, lead_id, self._request(agent_id))
                )
        self.assertEqual(sip.calls, 0)
        with SessionLocal() as db:
            session = db.scalar(select(VoiceSession))
            self.assertEqual(session.status, "cancelled")

    def test_disallowed_phone_country_is_rejected(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        request = self._request(agent_id)
        request.to_phone = "+14155552671"
        with SessionLocal() as db:
            with self.assertRaises(ValueError):
                asyncio.run(
                    OutboundVoiceCallService(
                        db, sip_service=FakeSip([]), runtime_backend=ReadyBackend([])
                    ).start_call(self.tenant.id, lead_id, request)
                )

    def test_cross_tenant_agent_is_rejected(self) -> None:
        self._configure_route()
        other_tenant, _ = self._seed_tenant_user(slug="outbound-b", email="outbound-b@example.com")
        other_agent = self._published_agent(other_tenant.id)
        lead_id, _ = self.seed_lead()
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "published version"):
                asyncio.run(
                    OutboundVoiceCallService(
                        db, sip_service=FakeSip([]), runtime_backend=ReadyBackend([])
                    ).start_call(self.tenant.id, lead_id, self._request(other_agent))
                )

    def test_cross_tenant_lead_is_rejected(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        other_tenant, _ = self._seed_tenant_user(
            slug="outbound-lead-b", email="outbound-lead-b@example.com"
        )
        lead_id, _ = self.seed_lead(tenant_id=other_tenant.id)
        with SessionLocal() as db:
            with self.assertRaisesRegex(ValueError, "does not belong"):
                asyncio.run(
                    OutboundVoiceCallService(
                        db, sip_service=FakeSip([]), runtime_backend=ReadyBackend([])
                    ).start_call(self.tenant.id, lead_id, self._request(agent_id))
                )

    def test_route_and_trunk_are_derived_from_tenant_not_request(self) -> None:
        self._configure_route()
        agent_id = self._published_agent()
        lead_id, _ = self.seed_lead()
        request = VoiceCallActionRequest.model_validate(
            {
                "agent_id": agent_id,
                "idempotency_key": "derived-route",
                "sip_route_id": "route-from-another-tenant",
                "livekit_outbound_trunk_id": "ST_other_tenant",
            }
        )
        sip = FakeSip([])
        with SessionLocal() as db:
            asyncio.run(
                OutboundVoiceCallService(
                    db, sip_service=sip, runtime_backend=ReadyBackend([])
                ).start_call(self.tenant.id, lead_id, request)
            )
        self.assertEqual(sip.last_kwargs["trunk_id"], "ST_tenant_a")

    @patch.object(OutboundVoiceCallService, "start_call", new_callable=AsyncMock)
    def test_crm_endpoint_routes_only_flagged_tenant_to_v2(self, start_call) -> None:
        self._enable_v2()
        lead_id, _ = self.seed_lead()
        start_call.return_value = {
            "status": "answered",
            "voice_call_id": "call-1",
            "voice_session_id": "session-1",
        }
        response = self.client.post(
            f"/api/v1/crm/leads/{lead_id}/actions/call",
            json={"agent_id": "agent-1", "idempotency_key": "request-1"},
        )
        self.assertEqual(response.status_code, 201)
        start_call.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
