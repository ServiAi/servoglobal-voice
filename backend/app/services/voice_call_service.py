from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.modules.crm.public import (
    CrmFacade,
    CrmVoiceCalls,
    VoiceCallView,
)
from app.schemas.integrations import (
    VoiceCallResponse,
)
from app.modules.integrations.public import IntegrationEvents

logger = logging.getLogger(__name__)


class VoiceCallService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.crm = CrmFacade(db)
        self.calls = CrmVoiceCalls(db)
        self.integration_event_service = IntegrationEvents(db)

    def list_lead_calls(self, tenant_id: str, lead_id: str) -> list[VoiceCallView]:
        return self.calls.list_for_lead(tenant_id, lead_id)

    def record_call_event(
        self,
        tenant_id: str,
        voice_call_id: str,
        provider: str,
        event_type: str,
        status: str,
        payload_summary: dict[str, Any],
    ) -> None:
        self.calls.add_event(
            tenant_id=tenant_id,
            voice_call_id=voice_call_id,
            provider=provider,
            event_type=event_type,
            status=status,
            payload_summary=self._sanitize_payload(payload_summary),
        )
        self.db.commit()

    def record_crm_activity(
        self,
        tenant_id: str,
        lead_id: str | None,
        contact_id: str,
        activity_type: str,
        title: str,
        description: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.crm.record_activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            payload=self._sanitize_payload(payload or {}),
        )

    def record_integration_event(
        self,
        tenant_id: str,
        provider: str,
        event_type: str,
        status: str,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.integration_event_service.record(
            tenant_id=tenant_id,
            provider=provider,
            event_type=event_type,
            status=status,
            message=message,
            metadata=metadata,
        )

    def mask_phone(self, phone: str | None) -> str | None:
        if not phone:
            return None
        digits = "".join(ch for ch in str(phone) if ch.isdigit())
        if len(digits) <= 4:
            return "***"
        return f"***{digits[-4:]}"

    def _safe_context(self, context: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for k, v in context.items():
            k_l = k.lower()
            if any(term in k_l for term in ("key", "secret", "auth", "token", "password")):
                continue
            safe[k] = v
        return safe

    def _sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for k, v in payload.items():
            k_l = k.lower()
            if any(term in k_l for term in ("phone", "telephone")):
                sanitized[k] = self.mask_phone(v) if isinstance(v, str) else "[redacted]"
            elif any(term in k_l for term in ("email", "name", "authorization", "token", "key", "secret")):
                sanitized[k] = "[redacted]"
            else:
                sanitized[k] = v
        return sanitized

    def responses_for_lead(self, tenant_id: str, lead_id: str) -> list[VoiceCallResponse]:
        from app.modules.agents.public import AgentsFacade
        from app.modules.voice.public import VoiceSessionFacade

        calls = self.list_lead_calls(tenant_id, lead_id)
        if not calls:
            return []
        agent_by_call = VoiceSessionFacade(self.db).agent_ids_by_crm_call(tenant_id, [call.id for call in calls])
        agent_names = AgentsFacade(self.db).agent_names(tenant_id, agent_by_call.values())
        names = {call_id: agent_names.get(agent_id) for call_id, agent_id in agent_by_call.items()}
        return [self.response(call, agent_name=names.get(call.id)) for call in calls]

    def response(self, call: VoiceCallView, *, agent_name: str | None = None) -> VoiceCallResponse:
        return VoiceCallResponse(
            id=call.id,
            provider=call.provider,
            provider_call_id=call.provider_call_id,
            provider_session_id=call.provider_session_id,
            provider_agent_id=call.provider_agent_id,
            agent_name=agent_name,
            direction=call.direction,
            status=call.status,
            started_at=call.started_at,
            answered_at=call.answered_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
            summary=call.summary,
            created_at=call.created_at,
        )
