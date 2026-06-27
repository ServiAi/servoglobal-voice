from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantEmailConfig


def validate_email(value: str | None, field_name: str = "email") -> str:
    cleaned = (value or "").strip()
    if "@" not in cleaned or "." not in cleaned.rsplit("@", 1)[-1]:
        raise ValueError(f"Invalid {field_name}.")
    return cleaned


class EmailConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_config(self, tenant_id: str, provider: str = "resend") -> TenantEmailConfig | None:
        return self.db.scalar(
            select(TenantEmailConfig).where(
                TenantEmailConfig.tenant_id == tenant_id,
                TenantEmailConfig.provider == provider,
            )
        )

    def get_active_config(self, tenant_id: str, provider: str = "resend") -> TenantEmailConfig:
        config = self.get_config(tenant_id, provider)
        if config is None or config.status != "active":
            raise ValueError("Email integration is not configured for this tenant.")
        return config

    def upsert_resend_config(
        self,
        *,
        tenant_id: str,
        sender_name: str | None,
        sender_email: str,
        reply_to: str | None,
        default_domain: str | None,
        status: str = "active",
    ) -> TenantEmailConfig:
        sender_email = validate_email(sender_email, "sender_email")
        reply_to_clean = validate_email(reply_to, "reply_to") if reply_to else None
        config = self.get_config(tenant_id, "resend")
        if config is None:
            config = TenantEmailConfig(tenant_id=tenant_id, provider="resend", sender_email=sender_email)
            self.db.add(config)
        config.sender_name = (sender_name or "").strip() or None
        config.sender_email = sender_email
        config.reply_to = reply_to_clean
        config.default_domain = (default_domain or "").strip() or None
        config.status = status
        config.last_error_message = None
        self.db.commit()
        self.db.refresh(config)
        return config

    def mark_health(self, config: TenantEmailConfig, *, status: str, error_message: str | None = None) -> None:
        config.status = status
        config.last_health_check_at = datetime.now(UTC)
        config.last_error_message = error_message
        self.db.commit()
