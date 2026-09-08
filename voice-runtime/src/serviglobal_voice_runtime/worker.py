from __future__ import annotations

import json
from typing import Any

from .config import Settings
from .control_plane import ControlPlaneClient
from .providers import RealtimeProviderFactory


def parse_session_id(metadata: str) -> str:
    try:
        value = json.loads(metadata)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid job metadata") from exc
    if not isinstance(value, dict) or set(value) != {"session_id"} or not isinstance(value["session_id"], str) or not value["session_id"]:
        raise ValueError("Job metadata must contain only session_id")
    return value["session_id"]


async def run_job(ctx: Any, settings: Settings) -> None:
    client = ControlPlaneClient(settings)
    session_id: str | None = None
    try:
        session_id = parse_session_id(ctx.job.metadata)
        spec = await client.get_session_spec(session_id)
        if spec.session_id != session_id:
            raise ValueError("Control Plane returned a different session_id")

        async def send_event(event_type: str, **kwargs: Any) -> None:
            await client.send_event(session_id, event_type, **kwargs)

        ctx.log_context_fields = {"voice_session_id": spec.session_id, "tenant_id": spec.tenant_id, "agent_id": spec.agent_id, "agent_version_id": spec.agent_version_id, "room_name": ctx.room.name, "provider": spec.runtime.realtime.provider, "livekit_job_id": ctx.job.id}
        await RealtimeProviderFactory(settings).resolve(spec.runtime.realtime.provider).run(ctx, spec, send_event)
    except Exception:
        if session_id:
            try:
                await client.send_event(session_id, "voice.session.failed", payload={"error_code": "runtime_failed"})
            except Exception:
                pass
        raise
    finally:
        await client.aclose()
