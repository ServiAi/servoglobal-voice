from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from livekit import api
from livekit.api.twirp_client import SipCallError

from app.core.config import settings
from app.services.livekit_sip_service import (
    LiveKitSipDialError,
    LiveKitSipService,
    map_sip_status,
)


class FakeSip:
    def __init__(self) -> None:
        self.items = []
        self.calls = []
        self.dial_error = None

    async def list_outbound_trunk(self, request):
        self.calls.append(("list", request))
        return SimpleNamespace(items=self.items)

    async def create_outbound_trunk(self, request):
        self.calls.append(("create", request))
        return api.SIPOutboundTrunkInfo(sip_trunk_id="ST_new")

    async def update_outbound_trunk(self, trunk_id, trunk):
        self.calls.append(("update", trunk_id, trunk))
        return api.SIPOutboundTrunkInfo(sip_trunk_id=trunk_id)

    async def delete_trunk(self, request):
        self.calls.append(("delete", request))

    async def create_sip_participant(self, request, *, timeout):
        self.calls.append(("dial", request, timeout))
        if self.dial_error:
            raise self.dial_error
        return api.SIPParticipantInfo(
            participant_id="PA_1",
            participant_identity=request.participant_identity,
            room_name=request.room_name,
            sip_call_id="SC_1",
        )


class FakeClient:
    def __init__(self, sip) -> None:
        self.sip = sip

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class LiveKitSipServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.sip = FakeSip()
        self.service = LiveKitSipService(lambda: FakeClient(self.sip))
        self.config = patch.multiple(
            settings,
            LIVEKIT_URL="wss://example.livekit.cloud",
            LIVEKIT_API_KEY="key",
            LIVEKIT_API_SECRET="secret",
        )
        self.config.start()

    def tearDown(self) -> None:
        self.config.stop()

    async def test_create_get_update_delete_trunk(self) -> None:
        created = await self.service.provision_outbound_trunk(
            trunk_id=None,
            name="serviglobal-route",
            address="pbx.example.com:5060",
            number="+573001112233",
            username="route-user",
            password="route-password",
        )
        self.assertEqual(created.sip_trunk_id, "ST_new")
        self.sip.items = [api.SIPOutboundTrunkInfo(sip_trunk_id="ST_existing")]
        self.assertEqual(
            (await self.service.get_outbound_trunk("ST_existing")).sip_trunk_id,
            "ST_existing",
        )
        updated = await self.service.provision_outbound_trunk(
            trunk_id="ST_existing",
            name="serviglobal-route",
            address="pbx.example.com:5060",
            number="+573001112233",
            username="route-user",
            password="route-password",
        )
        self.assertEqual(updated.sip_trunk_id, "ST_existing")
        await self.service.delete_outbound_trunk("ST_existing")
        self.assertIn("create", [call[0] for call in self.sip.calls])
        self.assertIn("update", [call[0] for call in self.sip.calls])
        self.assertIn("delete", [call[0] for call in self.sip.calls])

    async def test_dial_waits_for_answer_and_returns_sip_ids(self) -> None:
        result = await self.service.dial(
            trunk_id="ST_1",
            to_phone="+573009998888",
            from_number="+573001112233",
            room_name="sg-vs-session",
            participant_identity="sip-session",
        )
        request = self.sip.calls[-1][1]
        self.assertTrue(request.wait_until_answered)
        self.assertEqual(request.sip_trunk_id, "ST_1")
        self.assertEqual(result.sip_call_id, "SC_1")

    async def test_dial_maps_structured_sip_error(self) -> None:
        self.sip.dial_error = SipCallError(
            "unknown",
            "call failed",
            status=500,
            metadata={"sip_status_code": "486", "sip_status": "Busy Here"},
        )
        with self.assertRaises(LiveKitSipDialError) as caught:
            await self.service.dial(
                trunk_id="ST_1",
                to_phone="+573009998888",
                from_number="+573001112233",
                room_name="sg-vs-session",
                participant_identity="sip-session",
            )
        self.assertEqual(caught.exception.call_status, "busy")
        self.assertEqual(caught.exception.sip_status_code, 486)

    async def test_dial_maps_timeout_to_no_answer(self) -> None:
        self.sip.dial_error = TimeoutError()
        with self.assertRaises(LiveKitSipDialError) as caught:
            await self.service.dial(
                trunk_id="ST_1",
                to_phone="+573009998888",
                from_number="+573001112233",
                room_name="sg-vs-session",
                participant_identity="sip-session",
            )
        self.assertEqual(caught.exception.call_status, "no_answer")

    def test_status_mapping(self) -> None:
        self.assertEqual(map_sip_status(486), "busy")
        self.assertEqual(map_sip_status(603), "rejected")
        self.assertEqual(map_sip_status(408), "no_answer")
        self.assertEqual(map_sip_status(503), "failed")


if __name__ == "__main__":
    unittest.main()
