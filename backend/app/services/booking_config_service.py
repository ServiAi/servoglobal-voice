from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.integrations import TenantBookingConfig
from app.schemas.integrations import BookingConfigRequest, BookingConfigResponse
from app.services.calcom_client import CalComClient, CalComClientConfig, sanitize_calcom_error
from app.services.secret_manager_service import SecretManager


class BookingConfigService:
    def __init__(self, db: Session, secret_manager: SecretManager | None = None) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()

    def get_config(self, tenant_id: str) -> TenantBookingConfig | None:
        return self.db.scalar(
            select(TenantBookingConfig).where(
                TenantBookingConfig.tenant_id == tenant_id,
                TenantBookingConfig.provider == "calcom",
            )
        )

    def get_active_config(self, tenant_id: str) -> TenantBookingConfig:
        config = self.get_config(tenant_id)
        if not config or config.status not in {"active", "error"}:
            raise ValueError("Cal.com booking config is not active for this tenant.")
        if not config.cal_api_key_encrypted:
            raise ValueError("Cal.com API key is not configured for this tenant.")
        return config

    def upsert_calcom_config(self, tenant_id: str, body: BookingConfigRequest) -> TenantBookingConfig:
        if body.calendar_mode not in {"cal_managed", "crm_google_insert"}:
            raise ValueError("Invalid calendar_mode.")
        config = self.get_config(tenant_id)
        if config is None:
            config = TenantBookingConfig(tenant_id=tenant_id, provider="calcom")
            self.db.add(config)
        if not body.cal_api_key and not config.cal_api_key_encrypted:
            raise ValueError("Cal.com API key is required for the first configuration.")
        config.status = body.status
        config.calendar_mode = body.calendar_mode
        config.cal_api_version = body.cal_api_version or settings.CALCOM_API_VERSION
        config.organization_slug = body.organization_slug
        config.default_event_type_id = body.default_event_type_id
        config.default_event_type_slug = body.default_event_type_slug
        config.default_username = body.default_username
        config.default_team_slug = body.default_team_slug
        config.default_timezone = body.default_timezone
        config.default_language = body.default_language
        config.default_location_type = body.default_location_type
        config.default_length_minutes = body.default_length_minutes
        config.last_error_message = None
        if body.cal_api_key:
            config.cal_api_key_encrypted = self.secret_manager.encrypt_secret(body.cal_api_key)
        self.db.commit()
        self.db.refresh(config)
        return config

    def decrypt_calcom_api_key(self, config: TenantBookingConfig) -> str:
        if not config.cal_api_key_encrypted:
            raise ValueError("Cal.com API key is not configured for this tenant.")
        return self.secret_manager.decrypt_secret(config.cal_api_key_encrypted)

    def to_client_config(self, config: TenantBookingConfig) -> CalComClientConfig:
        return CalComClientConfig(
            api_key=self.decrypt_calcom_api_key(config),
            event_type_id=config.default_event_type_id,
            event_type_slug=config.default_event_type_slug,
            username=config.default_username,
            team_slug=config.default_team_slug,
            organization_slug=config.organization_slug,
            timezone=config.default_timezone,
            language=config.default_language,
            api_version=config.cal_api_version,
        )

    def test_connection(self, tenant_id: str) -> tuple[str, str | None]:
        config = self.get_active_config(tenant_id)
        try:
            CalComClient().get_available_slots(self.to_client_config(config), date_input=datetime.now(UTC).date().isoformat())
        except Exception as exc:
            message = sanitize_calcom_error(str(exc))
            self.mark_health(config, status="error", error_message=message)
            return "error", message
        self.mark_health(config, status="active", error_message=None)
        return "active", None

    def mark_health(self, config: TenantBookingConfig, *, status: str, error_message: str | None = None) -> None:
        config.last_health_check_at = datetime.now(UTC)
        config.last_error_message = error_message
        self.db.commit()

    def get_config_response(self, tenant_id: str) -> BookingConfigResponse:
        config = self.get_config(tenant_id)
        if config is None:
            return BookingConfigResponse(
                status="inactive",
                calendar_mode="cal_managed",
                has_secret=False,
                default_timezone=settings.GOOGLE_CALENDAR_DEFAULT_TIMEZONE,
                default_language="es",
                default_length_minutes=30,
            )
        return BookingConfigResponse(
            status=config.status,
            calendar_mode=config.calendar_mode,
            has_secret=bool(config.cal_api_key_encrypted),
            default_event_type_id=config.default_event_type_id,
            default_event_type_slug=config.default_event_type_slug,
            default_username=config.default_username,
            default_team_slug=config.default_team_slug,
            organization_slug=config.organization_slug,
            default_timezone=config.default_timezone,
            default_language=config.default_language,
            default_location_type=config.default_location_type,
            default_length_minutes=config.default_length_minutes,
            last_health_check_at=config.last_health_check_at,
            last_error_message=config.last_error_message,
        )
