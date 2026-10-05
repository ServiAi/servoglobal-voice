from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.modules.notifications.public import (
    NotificationDeliveryEvidence,
    NotificationSendResult,
    NotificationTemplate,
)


class DeliveryEvidencePort(Protocol):
    def find_delivery_evidence(
        self, *, tenant_id: str, delivery_id: str, fallback_message_id: str | None = None
    ) -> NotificationDeliveryEvidence | None: ...


class NotificationChannelPort(Protocol):
    def get_template(self, *, tenant_id: str, template_key: str | None) -> NotificationTemplate: ...

    def send_template(
        self,
        *,
        tenant_id: str,
        to_phone: str,
        template_key: str,
        variables: dict[str, str],
        metadata: dict[str, str],
        notification_delivery_id: str,
        lead_id: str | None,
        contact_id: str | None,
    ) -> NotificationSendResult: ...
