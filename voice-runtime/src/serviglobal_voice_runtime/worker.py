from __future__ import annotations

import json
import logging
from typing import Any

from .config import Settings
from .control_plane import ControlPlaneClient
from .credentials import ControlPlaneCredentialResolver, ProviderCredentialError
from .providers import RealtimeProviderFactory
from .call_factory import CallCreationFailed, CallCreationOutcomeUnknown

logger = logging.getLogger(__name__)


def parse_session_id(metadata: str) -> str:
    try:
        value = json.loads(metadata)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid job metadata") from exc
    if not isinstance(value, dict) or set(value) != {"session_id"} or not isinstance(value["session_id"], str) or not value["session_id"]:
        raise ValueError("Job metadata must contain only session_id")
    return value["session_id"]


async def _report_failure(client: ControlPlaneClient, session_id: str | None, error_code: str) -> None:
    if not session_id:
        return
    try:
        await client.send_event(session_id, "voice.session.failed", payload={"error_code": error_code})
    except Exception:
        pass


async def run_job(ctx: Any, settings: Settings) -> None:
    client = ControlPlaneClient(settings)
    credential_resolver = ControlPlaneCredentialResolver(client)
    session_id: str | None = None
    try:
        session_id = parse_session_id(ctx.job.metadata)
        spec = await client.get_session_spec(session_id)
        if spec.session_id != session_id:
            raise ValueError("Control Plane returned a different session_id")

        async def send_event(event_type: str, **kwargs: Any) -> None:
            await client.send_event(session_id, event_type, **kwargs)

        ctx.log_context_fields = {"voice_session_id": spec.session_id, "tenant_id": spec.tenant_id, "agent_id": spec.agent_id, "agent_version_id": spec.agent_version_id, "livekit_room_name": ctx.room.name, "provider": spec.runtime.realtime.provider, "livekit_job_id": ctx.job.id, "runtime_engine": "livekit"}
        logger.info("Voice runtime job starting", extra=ctx.log_context_fields)
        await RealtimeProviderFactory(settings, credential_resolver, client).resolve(spec.runtime.realtime.provider).run(ctx, spec, send_event)
    except ProviderCredentialError as exc:
        logger.error(
            "Voice runtime credential resolution failed",
            extra={"voice_session_id": session_id, "error_type": type(exc).__name__},
        )
        await _report_failure(client, session_id, "provider_credentials_unavailable")
        raise
    except CallCreationOutcomeUnknown as exc:
        logger.error(
            "Voice provider call creation outcome unknown",
            extra={"voice_session_id": session_id, "error_type": type(exc).__name__},
        )
        await _report_failure(client, session_id, "call_creation_outcome_unknown")
        raise
    except CallCreationFailed as exc:
        logger.error(
            "Voice provider call creation failed",
            extra={"voice_session_id": session_id, "error_type": type(exc).__name__},
        )
        await _report_failure(client, session_id, "call_creation_failed")
        raise
    except Exception as exc:
        logger.error(
            "Voice runtime job failed",
            extra={"voice_session_id": session_id, "error_type": type(exc).__name__},
        )
        await _report_failure(client, session_id, "runtime_failed")
        raise
    finally:
        await client.aclose()
