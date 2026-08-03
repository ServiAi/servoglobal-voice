from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth.deps import AuthContext, require_roles
from app.db.session import get_db
from app.schemas.notification_admin import (
    NotificationCapabilityItem,
    NotificationCapabilityUpdateRequest,
    NotificationCatalogResponse,
    NotificationDeliveryItem,
    NotificationDeliveryListResponse,
    NotificationOverviewResponse,
    NotificationRecipientCreateRequest,
    NotificationRecipientItem,
    NotificationRecipientUpdateRequest,
    NotificationRuleCreateRequest,
    NotificationRuleEnabledUpdateRequest,
    NotificationRuleItem,
    NotificationRuleUpdateRequest,
)
from app.services.notification_admin_service import NotificationAdminError, NotificationAdminService

router = APIRouter(prefix="/api/v1/admin/notifications", tags=["Notification Administration"])

_READ_ROLES = ["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"]
_WRITE_ROLES = ["platform_admin", "tenant_admin"]


def _raise_admin_error(exc: NotificationAdminError) -> None:
    status_code = {
        "conflict": status.HTTP_409_CONFLICT,
        "unprocessable": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }.get(exc.kind, status.HTTP_422_UNPROCESSABLE_ENTITY)
    raise HTTPException(status_code=status_code, detail=exc.code) from exc


def _rule_item(service: NotificationAdminService, rule) -> NotificationRuleItem:
    return NotificationRuleItem(
        id=rule.id,
        name=rule.name,
        capability_key=rule.capability_key,
        event_type=rule.event_type,
        channel=rule.channel,
        action_type=rule.action_type,
        template_key=rule.template_key,
        recipient_strategy=rule.recipient_strategy,
        recipient_group_key=rule.recipient_group_key,
        conditions_json=rule.conditions_json,
        variable_mapping_json=rule.variable_mapping_json,
        schedule_mode=rule.schedule_mode,
        schedule_offset_minutes=rule.schedule_offset_minutes,
        priority=rule.priority,
        enabled=rule.enabled,
        configuration_error=service.rule_configuration_error(rule),
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _recipient_item(recipient) -> NotificationRecipientItem:
    from app.services.whatsapp_message_service import mask_phone

    return NotificationRecipientItem(
        id=recipient.id,
        group_key=recipient.group_key,
        name=recipient.name,
        channel=recipient.channel,
        destination_masked=mask_phone(recipient.destination),
        status=recipient.status,
        created_at=recipient.created_at,
        updated_at=recipient.updated_at,
    )


@router.get("/overview", response_model=NotificationOverviewResponse)
def get_overview(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return NotificationAdminService(db).get_overview(tenant_id=context.tenant.id)


@router.get("/catalog", response_model=NotificationCatalogResponse)
def get_catalog(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return NotificationAdminService(db).get_catalog()


@router.get("/capabilities", response_model=list[NotificationCapabilityItem])
def list_capabilities(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return NotificationAdminService(db).list_capabilities(tenant_id=context.tenant.id)


@router.patch("/capabilities/{capability_key}", response_model=NotificationCapabilityItem)
def update_capability(
    capability_key: str,
    body: NotificationCapabilityUpdateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        return service.update_capability(
            tenant_id=context.tenant.id,
            capability_key=capability_key,
            enabled=body.enabled,
        )
    except NotificationAdminError as exc:
        _raise_admin_error(exc)


@router.get("/rules", response_model=list[NotificationRuleItem])
def list_rules(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    return [_rule_item(service, rule) for rule in service.list_rules(tenant_id=context.tenant.id)]


@router.post("/rules", response_model=NotificationRuleItem)
def create_rule(
    body: NotificationRuleCreateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        rule = service.create_rule(tenant_id=context.tenant.id, payload=body)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    return _rule_item(service, rule)


@router.patch("/rules/{rule_id}", response_model=NotificationRuleItem)
def update_rule(
    rule_id: str,
    body: NotificationRuleUpdateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        rule = service.update_rule(tenant_id=context.tenant.id, rule_id=rule_id, payload=body)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule_not_found")
    return _rule_item(service, rule)


@router.patch("/rules/{rule_id}/enabled", response_model=NotificationRuleItem)
def update_rule_enabled(
    rule_id: str,
    body: NotificationRuleEnabledUpdateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        rule = service.set_rule_enabled(tenant_id=context.tenant.id, rule_id=rule_id, enabled=body.enabled)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule_not_found")
    return _rule_item(service, rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> None:
    service = NotificationAdminService(db)
    try:
        deleted = service.delete_rule(tenant_id=context.tenant.id, rule_id=rule_id)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="rule_not_found")


@router.get("/recipients", response_model=list[NotificationRecipientItem])
def list_recipients(
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    return [_recipient_item(recipient) for recipient in service.list_recipients(tenant_id=context.tenant.id)]


@router.post("/recipients", response_model=NotificationRecipientItem)
def create_recipient(
    body: NotificationRecipientCreateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        recipient = service.create_recipient(tenant_id=context.tenant.id, payload=body)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    return _recipient_item(recipient)


@router.patch("/recipients/{recipient_id}", response_model=NotificationRecipientItem)
def update_recipient(
    recipient_id: str,
    body: NotificationRecipientUpdateRequest,
    context: AuthContext = Depends(require_roles(_WRITE_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    service = NotificationAdminService(db)
    try:
        recipient = service.update_recipient(tenant_id=context.tenant.id, recipient_id=recipient_id, payload=body)
    except NotificationAdminError as exc:
        _raise_admin_error(exc)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recipient_not_found")
    return _recipient_item(recipient)


@router.get("/deliveries", response_model=NotificationDeliveryListResponse)
def list_deliveries(
    page: int = 1,
    page_size: int = 25,
    status_filter: str | None = None,
    event_type: str | None = None,
    rule_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    return NotificationAdminService(db).list_deliveries(
        tenant_id=context.tenant.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        event_type=event_type,
        rule_id=rule_id,
        date_from=date_from,
        date_to=date_to,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
    )


@router.get("/deliveries/{delivery_id}", response_model=NotificationDeliveryItem)
def get_delivery(
    delivery_id: str,
    context: AuthContext = Depends(require_roles(_READ_ROLES)),
    db: Session = Depends(get_db),
) -> Any:
    delivery = NotificationAdminService(db).get_delivery(tenant_id=context.tenant.id, delivery_id=delivery_id)
    if delivery is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="delivery_not_found")
    return delivery
