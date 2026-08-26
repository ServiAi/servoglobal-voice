from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantSipRoute, TenantVoiceProviderConfig
from app.schemas.integrations import VoiceSipRouteRequest, VoiceSipRouteResponse
from app.services.secret_manager_service import SecretManager
from app.services.voice_phone_service import (
    SUPPORTED_OUTBOUND_COUNTRIES,
    normalize_caller_id,
)


HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
SIP_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
SIP_PASSWORD_FORBIDDEN = frozenset("\r\n;#[]")


class VoiceSipRouteService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    def get_route(self, tenant_id: str) -> TenantSipRoute | None:
        return self.db.scalar(
            select(TenantSipRoute).where(TenantSipRoute.tenant_id == tenant_id)
        )

    def get_active_route(self, tenant_id: str) -> TenantSipRoute:
        route = self.get_route(tenant_id)
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
        return route

    def upsert(
        self,
        tenant_id: str,
        provider_config: TenantVoiceProviderConfig,
        body: VoiceSipRouteRequest,
    ) -> TenantSipRoute:
        host = body.pbx_host.strip().lower()
        username = body.sip_username.strip()
        countries = sorted(set(body.allowed_countries))
        if not HOST_RE.fullmatch(host):
            raise ValueError("PBX host must be a hostname or IP address without protocol or port.")
        if not SIP_USERNAME_RE.fullmatch(username):
            raise ValueError("SIP username contains unsupported characters.")
        if body.sip_password and (
            any(char in SIP_PASSWORD_FORBIDDEN for char in body.sip_password)
            or not body.sip_password.isascii()
            or not body.sip_password.isprintable()
        ):
            raise ValueError("SIP password contains unsupported characters.")
        if not countries or any(code not in SUPPORTED_OUTBOUND_COUNTRIES for code in countries):
            raise ValueError("At least one supported outbound country is required.")
        if body.default_country not in countries:
            raise ValueError("Default country must be enabled for the SIP route.")

        route = self.get_route(tenant_id)
        is_new = route is None
        username_owner = self.db.scalar(
            select(TenantSipRoute).where(TenantSipRoute.sip_username == username)
        )
        if username_owner is not None and username_owner.tenant_id != tenant_id:
            raise ValueError("SIP username is already assigned to another tenant.")
        previous_pjsip_state = None if is_new else (
            route.status,
            route.sip_username,
            route.caller_id,
            False,
        )
        if route is None:
            route = TenantSipRoute(
                tenant_id=tenant_id,
                provider_config_id=provider_config.id,
                pbx_host=host,
                sip_username=username,
                caller_id="",
            )
            self.db.add(route)
        elif route.provider_config_id != provider_config.id:
            raise ValueError("SIP route does not belong to the selected voice provider.")

        if body.sip_password:
            route.sip_password_encrypted = self.secret_manager.encrypt_secret(body.sip_password)
        elif is_new and body.status == "active":
            raise ValueError("SIP password is required when activating a new route.")

        route.status = body.status
        route.pbx_host = host
        route.pbx_port = body.pbx_port
        route.sip_username = username
        route.caller_id = normalize_caller_id(
            body.caller_id, default_country=body.default_country
        )
        route.default_country = body.default_country
        route.allowed_countries_json = countries
        route.max_concurrent_calls = body.max_concurrent_calls
        if route.status == "active" and not route.sip_password_encrypted:
            raise ValueError("SIP password is required before activating the route.")
        current_pjsip_state = (
            route.status,
            route.sip_username,
            route.caller_id,
            bool(body.sip_password),
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

    @staticmethod
    def response(route: TenantSipRoute | None) -> VoiceSipRouteResponse | None:
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
            allowed_countries=list(route.allowed_countries_json),
            max_concurrent_calls=route.max_concurrent_calls,
            has_sip_password=bool(route.sip_password_encrypted),
            provision_status=route.provision_status,
            desired_revision=route.desired_revision,
            applied_revision=route.applied_revision,
            provision_error_code=route.provision_error_code,
            provisioned_at=route.provisioned_at,
            last_provision_attempt_at=route.last_provision_attempt_at,
        )
