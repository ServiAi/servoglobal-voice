from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.notifications import TenantNotificationRule


class NotificationRuleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_active_rules(self, *, tenant_id: str, event_type: str) -> list[TenantNotificationRule]:
        return (
            self.db.query(TenantNotificationRule)
            .filter(
                TenantNotificationRule.tenant_id == tenant_id,
                TenantNotificationRule.event_type == event_type,
                TenantNotificationRule.enabled.is_(True),
            )
            .order_by(
                TenantNotificationRule.priority.asc(),
                TenantNotificationRule.created_at.asc(),
                TenantNotificationRule.id.asc(),
            )
            .all()
        )
