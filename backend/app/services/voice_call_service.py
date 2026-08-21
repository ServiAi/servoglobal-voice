from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmLead, CrmVoiceCall, CrmVoiceCallEvent
from app.schemas.integrations import VoiceCallActionRequest, VoiceCallActionResponse, VoiceCallResponse
from app.services.voice_client import VoiceClient, VoiceClientConfig, VoiceSipRouteConfig
from app.services.voice_config_service import VoiceConfigService
from app.services.voice_sip_route_service import VoiceSipRouteService
from app.services.voice_agent_service import VoiceAgentService
from app.services.crm_activity_service import CrmActivityService
from app.services.integration_event_service import IntegrationEventService

logger = logging.getLogger(__name__)


class VoiceCallService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config_service = VoiceConfigService(db)
        self.route_service = VoiceSipRouteService(db, self.config_service.secret_manager)
        self.agent_service = VoiceAgentService(db)
        self.activity_service = CrmActivityService(db)
        self.integration_event_service = IntegrationEventService(db)

    def start_lead_call(
        self,
        tenant_id: str,
        lead_id: str,
        body: VoiceCallActionRequest,
    ) -> VoiceCallActionResponse:
        lead = self.db.get(CrmLead, lead_id)
        if not lead or lead.tenant_id != tenant_id:
            raise ValueError("Lead does not exist or does not belong to this tenant.")

        contact = lead.contact
        if not contact or contact.tenant_id != tenant_id:
            raise ValueError("Contact associated with this lead does not exist.")

        to_phone = body.to_phone or contact.phone
        if not to_phone:
            raise ValueError("El contacto no tiene teléfono para iniciar una llamada.")

        provider_config = self.config_service.get_active_provider_config(tenant_id, "ultravox")
        api_key = self.config_service.decrypt_api_key(provider_config)
        sip_route = self.route_service.get_active_route(tenant_id)
        if sip_route.provider_config_id != provider_config.id:
            raise ValueError("Outbound SIP route is not linked to the active voice provider.")

        if body.agent_config_id:
            agent_config = self.agent_service.validate_agent_belongs_to_tenant(tenant_id, body.agent_config_id)
        else:
            agent_config = self.agent_service.get_default_agent(tenant_id, provider_config.provider)
            if not agent_config:
                raise ValueError("No active voice agent config found for this tenant.")

        voice_call = CrmVoiceCall(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact.id,
            provider=provider_config.provider,
            provider_agent_id=agent_config.provider_agent_id,
            direction="outbound",
            status="requested",
            to_phone=to_phone,
            from_number=sip_route.caller_id,
        )
        self.db.add(voice_call)
        self.db.commit()
        self.db.refresh(voice_call)

        metadata = {
            "tenant_id": tenant_id,
            "lead_id": lead_id,
            "contact_id": contact.id,
            "voice_call_id": voice_call.id,
            "source": "serviglobal_crm",
        }

        context = {
            "contact_name": contact.name,
            "contact_phone": to_phone,
            "company": contact.company,
        }
        if body.context:
            context.update(body.context)

        context = self._safe_context(context)

        client = VoiceClient()

        try:
            client_config = VoiceClientConfig(
                provider=provider_config.provider,
                api_key=api_key,
                base_url=provider_config.base_url,
                default_language=provider_config.default_language,
                default_timezone=provider_config.default_timezone,
                sip_route=VoiceSipRouteConfig(
                    host=sip_route.pbx_host,
                    port=sip_route.pbx_port,
                    username=sip_route.sip_username,
                    password=self.route_service.decrypt_password(sip_route),
                    caller_id=sip_route.caller_id,
                    default_country=sip_route.default_country,
                    allowed_countries=tuple(sip_route.allowed_countries_json),
                ),
            )
            response = client.start_outbound_call(
                client_config,
                to_phone=to_phone,
                agent_id=agent_config.provider_agent_id,
                metadata=metadata,
                context=context,
            )

            norm = client.normalize_provider_response(provider_config.provider, response)
            voice_call.provider_call_id = norm.get("provider_call_id")
            voice_call.provider_session_id = norm.get("provider_session_id")
            voice_call.status = "queued"
            voice_call.started_at = datetime.now(UTC)
            self.db.commit()

            self.record_call_event(
                tenant_id=tenant_id,
                voice_call_id=voice_call.id,
                provider=provider_config.provider,
                event_type="call_requested",
                status="success",
                payload_summary={"provider_call_id": voice_call.provider_call_id},
            )

            self.record_crm_activity(
                tenant_id=tenant_id,
                lead_id=lead_id,
                contact_id=contact.id,
                activity_type="voice_call_requested",
                title="Llamada saliente iniciada",
                description=f"Se solicitó el inicio de llamada a través del agente {agent_config.display_name}.",
                payload={"voice_call_id": voice_call.id, "provider": provider_config.provider, "status": "requested"},
            )

            self.record_integration_event(
                tenant_id=tenant_id,
                provider=provider_config.provider,
                event_type="call_start",
                status="success",
                metadata={"voice_call_id": voice_call.id, "provider_call_id": voice_call.provider_call_id},
            )

            return VoiceCallActionResponse(
                status=voice_call.status,
                voice_call_id=voice_call.id,
                provider_call_id=voice_call.provider_call_id,
                provider_session_id=voice_call.provider_session_id,
            )

        except Exception as e:
            voice_call.status = "failed"
            voice_call.error_message = client.sanitize_voice_error(e)
            self.db.commit()

            self.record_call_event(
                tenant_id=tenant_id,
                voice_call_id=voice_call.id,
                provider=provider_config.provider,
                event_type="call_failed",
                status="failed",
                payload_summary={"error": voice_call.error_message},
            )

            self.record_crm_activity(
                tenant_id=tenant_id,
                lead_id=lead_id,
                contact_id=contact.id,
                activity_type="voice_call_failed",
                title="Llamada saliente fallida",
                description=f"Error al iniciar llamada: {voice_call.error_message}",
                payload={"voice_call_id": voice_call.id, "error": voice_call.error_message},
            )

            self.record_integration_event(
                tenant_id=tenant_id,
                provider=provider_config.provider,
                event_type="call_start",
                status="failed",
                message=voice_call.error_message,
                metadata={"voice_call_id": voice_call.id},
            )

            raise ValueError(f"Failed to initiate voice call: {voice_call.error_message}")

    def list_lead_calls(self, tenant_id: str, lead_id: str) -> list[CrmVoiceCall]:
        lead = self.db.get(CrmLead, lead_id)
        if not lead or lead.tenant_id != tenant_id:
            return []

        return list(
            self.db.scalars(
                select(CrmVoiceCall)
                .where(
                    CrmVoiceCall.tenant_id == tenant_id,
                    CrmVoiceCall.lead_id == lead_id,
                )
                .order_by(CrmVoiceCall.created_at.desc())
            ).all()
        )

    def record_call_event(
        self,
        tenant_id: str,
        voice_call_id: str,
        provider: str,
        event_type: str,
        status: str,
        payload_summary: dict[str, Any],
    ) -> CrmVoiceCallEvent:
        event = CrmVoiceCallEvent(
            tenant_id=tenant_id,
            voice_call_id=voice_call_id,
            provider=provider,
            event_type=event_type,
            status=status,
            payload_summary_json=self._sanitize_payload(payload_summary),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

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
        self.activity_service.create_activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            contact_id=contact_id,
            activity_type=activity_type,
            title=title,
            description=description,
            payload_json=self._sanitize_payload(payload or {}),
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
        self.integration_event_service.record_event(
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

    def response(self, call: CrmVoiceCall) -> VoiceCallResponse:
        return VoiceCallResponse(
            id=call.id,
            provider=call.provider,
            provider_call_id=call.provider_call_id,
            provider_session_id=call.provider_session_id,
            provider_agent_id=call.provider_agent_id,
            direction=call.direction,
            status=call.status,
            started_at=call.started_at,
            answered_at=call.answered_at,
            ended_at=call.ended_at,
            duration_seconds=call.duration_seconds,
            summary=call.summary,
            created_at=call.created_at,
        )
