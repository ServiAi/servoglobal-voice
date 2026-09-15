from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.core.config import settings


@dataclass(frozen=True)
class LiveKitSipDialResult:
    participant_id: str
    participant_identity: str
    room_name: str
    sip_call_id: str


class LiveKitSipError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LiveKitSipDialError(LiveKitSipError):
    def __init__(self, status: str, sip_status_code: int | None = None) -> None:
        super().__init__(f"livekit_sip_{status}")
        self.call_status = status
        self.sip_status_code = sip_status_code


def map_sip_status(code: int | None) -> str:
    if code == 486:
        return "busy"
    if code in {603, 607, 608}:
        return "rejected"
    if code in {408, 480, 487}:
        return "no_answer"
    return "failed"


class LiveKitSipService:
    def __init__(self, client_factory: Callable | None = None) -> None:
        self._client_factory = client_factory

    @staticmethod
    def _require_configured() -> None:
        if not all((settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)):
            raise LiveKitSipError("livekit_sip_not_configured")

    def _client(self):
        self._require_configured()
        if self._client_factory is not None:
            return self._client_factory()
        from livekit import api

        return api.LiveKitAPI(
            settings.LIVEKIT_URL,
            settings.LIVEKIT_API_KEY,
            settings.LIVEKIT_API_SECRET,
        )

    @staticmethod
    def _trunk(*, name: str, address: str, number: str, username: str, password: str):
        from livekit import api

        return api.SIPOutboundTrunkInfo(
            name=name,
            address=address,
            transport=api.SIPTransport.SIP_TRANSPORT_UDP,
            numbers=[number],
            auth_username=username,
            auth_password=password,
        )

    async def provision_outbound_trunk(
        self,
        *,
        trunk_id: str | None,
        name: str,
        address: str,
        number: str,
        username: str,
        password: str,
    ):
        if trunk_id and await self.get_outbound_trunk(trunk_id) is not None:
            return await self.update_outbound_trunk(
                trunk_id,
                name=name,
                address=address,
                number=number,
                username=username,
                password=password,
            )
        from livekit import api

        trunk = self._trunk(
            name=name,
            address=address,
            number=number,
            username=username,
            password=password,
        )
        async with self._client() as client:
            return await client.sip.create_outbound_trunk(
                api.CreateSIPOutboundTrunkRequest(trunk=trunk)
            )

    async def get_outbound_trunk(self, trunk_id: str):
        from livekit import api

        async with self._client() as client:
            response = await client.sip.list_outbound_trunk(
                api.ListSIPOutboundTrunkRequest(trunk_ids=[trunk_id])
            )
        return next((item for item in response.items if item.sip_trunk_id == trunk_id), None)

    async def update_outbound_trunk(
        self,
        trunk_id: str,
        *,
        name: str,
        address: str,
        number: str,
        username: str,
        password: str,
    ):
        trunk = self._trunk(
            name=name,
            address=address,
            number=number,
            username=username,
            password=password,
        )
        async with self._client() as client:
            return await client.sip.update_outbound_trunk(trunk_id, trunk)

    async def delete_outbound_trunk(self, trunk_id: str) -> None:
        from livekit import api

        async with self._client() as client:
            await client.sip.delete_trunk(api.DeleteSIPTrunkRequest(sip_trunk_id=trunk_id))

    async def dial(
        self,
        *,
        trunk_id: str,
        to_phone: str,
        from_number: str,
        room_name: str,
        participant_identity: str,
    ) -> LiveKitSipDialResult:
        from livekit import api
        from livekit.api.twirp_client import SipCallError

        request = api.CreateSIPParticipantRequest(
            sip_trunk_id=trunk_id,
            sip_call_to=to_phone,
            sip_number=from_number,
            room_name=room_name,
            participant_identity=participant_identity,
            participant_name="ServiGlobal outbound",
            wait_until_answered=True,
        )
        try:
            async with self._client() as client:
                result = await client.sip.create_sip_participant(
                    request,
                    timeout=settings.LIVEKIT_SIP_DIAL_TIMEOUT_SECONDS,
                )
        except SipCallError as exc:
            raise LiveKitSipDialError(
                map_sip_status(exc.sip_status_code), exc.sip_status_code
            ) from None
        except TimeoutError:
            raise LiveKitSipDialError("no_answer", 408) from None
        except Exception:
            raise LiveKitSipDialError("failed") from None
        return LiveKitSipDialResult(
            participant_id=result.participant_id,
            participant_identity=result.participant_identity,
            room_name=result.room_name,
            sip_call_id=result.sip_call_id,
        )
