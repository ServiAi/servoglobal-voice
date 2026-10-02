from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.telephony.domain.phone_numbers import normalize_caller_id
from app.modules.telephony.domain.routes import (
    normalize_allowed_countries,
    normalize_route_host,
    sip_username_for_route,
    validate_sip_password,
)
from app.modules.telephony.domain.views import (
    SipRouteConnection,
    SipRouteSettings,
    SipRouteView,
)
from app.modules.telephony.infrastructure.livekit_sip import (
    LiveKitSipError,
    LiveKitSipService,
)
from app.modules.telephony.infrastructure.models import TenantSipRoute
from app.modules.voice_providers.public import ProviderConfigRef
from app.services.secret_manager_service import SecretManager


class SipRouteService:
    """A tenant's SIP route: configuration, activation checks, secret
    handling and LiveKit trunk provisioning. Works on TenantSipRoute rows
    internally; other modules get SipRouteView / SipRouteConnection."""

    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    # -- queries (ORM, inside Telephony) -------------------------------------

    def get_route(self, tenant_id: str, *, for_update: bool = False) -> TenantSipRoute | None:
        query = select(TenantSipRoute).where(TenantSipRoute.tenant_id == tenant_id)
        if for_update:
            query = query.with_for_update()
        return self.db.scalar(query)

    def get_route_by_id(self, route_id: str, *, for_update: bool = False) -> TenantSipRoute | None:
        query = select(TenantSipRoute).where(TenantSipRoute.id == route_id)
        if for_update:
            query = query.with_for_update()
        return self.db.scalar(query)

    def get_active_route(
        self,
        tenant_id: str,
        *,
        for_update: bool = False,
        require_livekit: bool = False,
    ) -> TenantSipRoute:
        route = self.get_route(tenant_id, for_update=for_update)
        if route is None:
            raise ValueError(
                "Este tenant no tiene una ruta SIP saliente configurada. "
                "Configúrala en Integraciones > Voz antes de iniciar llamadas."
            )
        if route.status != "active":
            raise ValueError(
                "La ruta SIP saliente de este tenant está inactiva. "
                "Actívala en Integraciones > Voz antes de iniciar llamadas."
            )
        if not route.sip_password_encrypted:
            raise ValueError(
                "La ruta SIP saliente de este tenant no tiene contraseña configurada. "
                "Complétala en Integraciones > Voz antes de iniciar llamadas."
            )
        if (
            route.provision_status != "active"
            or route.applied_revision != route.desired_revision
        ):
            raise ValueError(
                "La ruta SIP todavía no está aplicada en Asterisk. "
                "Espera la confirmación del aprovisionador antes de iniciar llamadas."
            )
        if require_livekit and (
            route.livekit_provision_status != "active"
            or not route.livekit_outbound_trunk_id
        ):
            raise ValueError("La ruta SIP todavía no está aprovisionada en LiveKit.")
        return route

    # -- configuration -------------------------------------------------------

    def upsert(
        self,
        tenant_id: str,
        provider_config: ProviderConfigRef,
        settings: SipRouteSettings,
    ) -> TenantSipRoute:
        if provider_config.tenant_id != tenant_id:
            raise ValueError("SIP route does not belong to the selected voice provider.")
        host = normalize_route_host(settings.pbx_host)
        validate_sip_password(settings.sip_password)
        countries = normalize_allowed_countries(settings.allowed_countries, settings.default_country)

        route = self.get_route(tenant_id)
        is_new = route is None
        previous_pjsip_state = None if is_new else (
            route.status,
            route.sip_username,
            route.caller_id,
            False,
        )
        if route is None:
            route_id = str(uuid4())
            route = TenantSipRoute(
                id=route_id,
                tenant_id=tenant_id,
                provider_config_id=provider_config.id,
                pbx_host=host,
                sip_username=sip_username_for_route(route_id),
                caller_id="",
            )
            self.db.add(route)
        elif route.provider_config_id is None:
            route.provider_config_id = provider_config.id
        elif route.provider_config_id != provider_config.id:
            raise ValueError("SIP route does not belong to the selected voice provider.")

        if settings.sip_password:
            route.sip_password_encrypted = self.secret_manager.encrypt_secret(settings.sip_password)
        elif is_new and settings.status == "active":
            raise ValueError("SIP password is required when activating a new route.")

        route.status = settings.status
        route.pbx_host = host
        route.pbx_port = settings.pbx_port
        route.sip_username = sip_username_for_route(route.id)
        route.caller_id = normalize_caller_id(
            settings.caller_id, default_country=settings.default_country
        )
        route.default_country = settings.default_country
        route.allowed_countries_json = countries
        route.max_concurrent_calls = settings.max_concurrent_calls
        if route.status == "active" and not route.sip_password_encrypted:
            raise ValueError("SIP password is required before activating the route.")
        current_pjsip_state = (
            route.status,
            route.sip_username,
            route.caller_id,
            bool(settings.sip_password),
        )
        if is_new:
            if route.status == "active":
                route.desired_revision = 1
                route.provision_status = "pending"
        elif previous_pjsip_state != current_pjsip_state:
            route.desired_revision += 1
            route.provision_status = "pending"
            route.provision_error_code = None
        self.db.flush()
        return route

    def decrypt_password(self, route: TenantSipRoute) -> str:
        if not route.sip_password_encrypted:
            raise ValueError("SIP password is not configured.")
        return self.secret_manager.decrypt_secret(route.sip_password_encrypted)

    # -- LiveKit trunk -------------------------------------------------------

    async def provision_livekit_outbound(self, route: TenantSipRoute, sip_service=None) -> TenantSipRoute:
        route.livekit_provision_status = "pending"
        route.livekit_provision_error_code = None
        self.db.commit()
        try:
            trunk = await (sip_service or LiveKitSipService()).provision_outbound_trunk(
                trunk_id=route.livekit_outbound_trunk_id,
                name=f"serviglobal-{route.id}",
                address=f"{route.pbx_host}:{route.pbx_port}",
                number=route.caller_id,
                username=route.sip_username,
                password=self.decrypt_password(route),
            )
        except Exception as exc:
            route.livekit_provision_status = "failed"
            route.livekit_provision_error_code = (
                exc.code if isinstance(exc, LiveKitSipError) else "livekit_sip_provision_failed"
            )
            self.db.commit()
            raise ValueError("LiveKit SIP trunk provisioning failed.") from None
        route.livekit_outbound_trunk_id = trunk.sip_trunk_id
        route.livekit_provision_status = "active"
        route.livekit_provision_error_code = None
        route.livekit_provisioned_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(route)
        return route

    async def deprovision_livekit_outbound(self, route: TenantSipRoute, sip_service=None) -> TenantSipRoute:
        if route.livekit_outbound_trunk_id:
            try:
                await (sip_service or LiveKitSipService()).delete_outbound_trunk(
                    route.livekit_outbound_trunk_id
                )
            except Exception:
                route.livekit_provision_status = "failed"
                route.livekit_provision_error_code = "livekit_sip_delete_failed"
                self.db.commit()
                raise ValueError("LiveKit SIP trunk deletion failed.") from None
        route.livekit_outbound_trunk_id = None
        route.livekit_provision_status = "disabled"
        route.livekit_provision_error_code = None
        route.livekit_provisioned_at = None
        self.db.commit()
        self.db.refresh(route)
        return route

    async def sync_livekit_trunk(self, tenant_id: str, sip_service=None) -> None:
        """Provision the tenant's LiveKit trunk when the route is active,
        remove a stale one when it is not. No route: nothing to do."""
        route = self.get_route(tenant_id)
        if route is not None and route.status == "active":
            await self.provision_livekit_outbound(route, sip_service)
        elif route is not None and route.livekit_outbound_trunk_id:
            await self.deprovision_livekit_outbound(route, sip_service)

    # -- views (DTOs for other modules) --------------------------------------

    @staticmethod
    def view(route: TenantSipRoute | None) -> SipRouteView | None:
        if route is None:
            return None
        return SipRouteView(
            id=route.id,
            tenant_id=route.tenant_id,
            provider_config_id=route.provider_config_id,
            status=route.status,
            pbx_host=route.pbx_host,
            pbx_port=route.pbx_port,
            sip_username=route.sip_username,
            caller_id=route.caller_id,
            default_country=route.default_country,
            allowed_countries=tuple(route.allowed_countries_json),
            max_concurrent_calls=route.max_concurrent_calls,
            has_sip_password=bool(route.sip_password_encrypted),
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

    def connection(self, route: TenantSipRoute) -> SipRouteConnection:
        return SipRouteConnection(
            route_id=route.id,
            provider_config_id=route.provider_config_id,
            host=route.pbx_host,
            port=route.pbx_port,
            username=route.sip_username,
            password=self.decrypt_password(route),
            caller_id=route.caller_id,
            default_country=route.default_country,
            allowed_countries=tuple(route.allowed_countries_json),
        )
