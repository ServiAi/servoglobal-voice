from sqlalchemy.orm import Session

from app.modules.identity.infrastructure.models import AccessAuditLog


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        user_id: str | None,
        tenant_id: str | None,
        action: str,
        resource: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.db.add(AccessAuditLog(
            user_id=user_id,
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            ip_address=ip_address,
            user_agent=user_agent,
        ))
        self.db.commit()
