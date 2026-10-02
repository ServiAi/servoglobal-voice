from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.integrations import TenantVoiceProviderConfig
from app.modules.telephony.public import SipRouteFacade, SipRouteSettings, SipRouteView
from app.modules.voice_providers.public import ProviderConfigRef
from app.schemas.integrations import (
    VoiceProviderConfigRequest,
    VoiceProviderConfigResponse,
    VoiceSipRouteResponse,
)
from app.services.integration_event_service import IntegrationEventService
from app.services.secret_manager_service import SecretManager
from app.services.voice_provider_config_store import VoiceProviderConfigStore


class VoiceConfigService(VoiceProviderConfigStore):
    """Provider configuration management for the Integrations UI/API: the
    store (lookup + secrets) plus config upsert/health and the tenant's SIP
    route, which is Telephony's (SipRouteFacade)."""

    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        super().__init__(db, secret_manager)
        self.event_service = IntegrationEventService(db)
        self.route_service = SipRouteFacade(db, self.secret_manager)

    def upsert_provider_config(self, tenant_id: str, body: VoiceProviderConfigRequest) -> TenantVoiceProviderConfig:
        config = self.get_provider_config(tenant_id, body.provider)
        
        is_new = False
        if config is None:
            config = TenantVoiceProviderConfig(tenant_id=tenant_id, provider=body.provider)
            self.db.add(config)
            is_new = True

        if body.api_key:
            config.api_key_encrypted = self.secret_manager.encrypt_secret(body.api_key)
        elif is_new:
            raise ValueError("API key is required for the first integration setup.")

        if body.webhook_secret:
            config.webhook_secret_encrypted = self.secret_manager.encrypt_secret(body.webhook_secret)

        config.status = body.status
        config.display_name = body.display_name or "Voice Integration"
        config.base_url = body.base_url
        config.default_voice_agent_id = body.default_voice_agent_id
        config.default_from_number = body.default_from_number
        config.default_language = body.default_language
        config.default_timezone = body.default_timezone
        config.last_error_message = None

        if body.sip_route is not None:
            self.db.flush()
            self.route_service.upsert(
                tenant_id,
                ProviderConfigRef(id=config.id, tenant_id=config.tenant_id, provider=config.provider),
                SipRouteSettings(
                    status=body.sip_route.status,
                    pbx_host=body.sip_route.pbx_host,
                    pbx_port=body.sip_route.pbx_port,
                    sip_password=body.sip_route.sip_password,
                    caller_id=body.sip_route.caller_id,
                    default_country=body.sip_route.default_country,
                    allowed_countries=tuple(body.sip_route.allowed_countries),
                    max_concurrent_calls=body.sip_route.max_concurrent_calls,
                ),
            )

        self.db.commit()
        self.db.refresh(config)

        self.event_service.record_event(
            tenant_id=tenant_id,
            provider=body.provider,
            event_type="config_updated",
            status="success",
            resource_type="config",
            resource_id=config.id,
            metadata={"has_secret": bool(config.api_key_encrypted), "status": config.status},
        )

        return config

    def test_connection(self, tenant_id: str, provider: str = "ultravox") -> tuple[str, str | None]:
        from app.services.ultravox_provider_client import UltravoxProviderClient

        config = self.get_active_provider_config(tenant_id, provider)
        try:
            UltravoxProviderClient().list_agents(
                self.decrypt_api_key(config), cursor=None, page_size=1, search=None
            )

            self.mark_health(config, status="active", error_message=None)
            return "active", None
        except Exception as exc:
            message = getattr(exc, "code", "provider_unavailable")
            self.mark_health(config, status="error", error_message=message)
            return "error", message

    def mark_health(self, config: TenantVoiceProviderConfig, *, status: str, error_message: str | None = None) -> None:
        config.last_health_check_at = datetime.now(UTC)
        config.last_error_message = error_message
        self.db.commit()

    @staticmethod
    def _route_response(route: SipRouteView | None) -> VoiceSipRouteResponse | None:
        """Telephony's SipRouteView as the (unchanged) HTTP contract."""
        if route is None:
            return None
        return VoiceSipRouteResponse(
            id=route.id,
            status=route.status,
            pbx_host=route.pbx_host,
            pbx_port=route.pbx_port,
            sip_username=route.sip_username,
            caller_id=route.caller_id,
            default_country=route.default_country,
            allowed_countries=list(route.allowed_countries),
            max_concurrent_calls=route.max_concurrent_calls,
            has_sip_password=route.has_sip_password,
            provision_status=route.provision_status,
            desired_revision=route.desired_revision,
            applied_revision=route.applied_revision,
            provision_error_code=route.provision_error_code,
            provisioned_at=route.provisioned_at,
            last_provision_attempt_at=route.last_provision_attempt_at,
            livekit_outbound_trunk_id=route.livekit_outbound_trunk_id,
            livekit_provision_status=route.livekit_provision_status,
            livekit_provision_error_code=route.livekit_provision_error_code,
            livekit_provisioned_at=route.livekit_provisioned_at,
        )

    def get_config_response(self, tenant_id: str, provider: str = "ultravox") -> VoiceProviderConfigResponse:
        config = self.get_provider_config(tenant_id, provider)
        if config is None:
            return VoiceProviderConfigResponse(
                id="",
                provider=provider,
                status="inactive",
                display_name=None,
                base_url=None,
                default_voice_agent_id=None,
                default_from_number=None,
                default_language="es",
                default_timezone="America/Bogota",
                has_secret=False,
                has_webhook_secret=False,
                last_health_check_at=None,
                last_error_message=None,
                sip_route=None,
            )
        route = self.route_service.get_route(tenant_id)
        return VoiceProviderConfigResponse(
            id=config.id,
            provider=config.provider,
            status=config.status,
            display_name=config.display_name,
            base_url="https://api.ultravox.ai",
            default_voice_agent_id=config.default_voice_agent_id,
            default_from_number=config.default_from_number,
            default_language=config.default_language,
            default_timezone=config.default_timezone,
            has_secret=bool(config.api_key_encrypted),
            has_webhook_secret=bool(config.webhook_secret_encrypted),
            last_health_check_at=config.last_health_check_at,
            last_error_message=config.last_error_message,
            sip_route=self._route_response(route),
        )
