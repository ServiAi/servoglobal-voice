from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class RuntimeDispatchResult:
    room_name: str
    dispatch_id: str


class LiveKitRuntimeBackend:
    async def close_session_room(self, session_id: str) -> None:
        """Confirm a session's room is gone before its agent can be deleted."""
        if not all((settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)):
            raise RuntimeError("LiveKit room management is not configured")
        from livekit import api

        room_name = f"sg-vs-{session_id}"
        async with api.LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET) as client:
            rooms = await client.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
            if rooms.rooms:
                try:
                    await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
                except Exception:
                    # A concurrent teardown may have removed it after the first read.
                    remaining = await client.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
                    if remaining.rooms:
                        raise
            remaining = await client.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
            if remaining.rooms:
                raise RuntimeError("LiveKit room closure could not be confirmed")

    async def dispatch(self, session_id: str) -> RuntimeDispatchResult:
        if not all((settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)):
            raise RuntimeError("LiveKit dispatch is not configured")
        from livekit import api

        room_name = f"sg-vs-{session_id}"
        async with api.LiveKitAPI(settings.LIVEKIT_URL, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET) as client:
            dispatch = await client.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=settings.LIVEKIT_AGENT_NAME,
                    room=room_name,
                    metadata=json.dumps({"session_id": session_id}, separators=(",", ":")),
                )
            )
        return RuntimeDispatchResult(room_name=room_name, dispatch_id=dispatch.id)
