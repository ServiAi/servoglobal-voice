from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class RuntimeDispatchResult:
    room_name: str
    dispatch_id: str


class LiveKitRuntimeBackend:
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
