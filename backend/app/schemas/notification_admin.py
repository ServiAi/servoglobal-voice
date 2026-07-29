from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationOverviewCapabilityCounts(BaseModel):
    total: int
    enabled: int


class NotificationOverviewRuleCounts(BaseModel):
    total: int
    enabled: int


class NotificationOverviewRecipientCounts(BaseModel):
    total: int
    active: int


class NotificationOverviewDeliveryCounts(BaseModel):
    pending: int = 0
    processing: int = 0
    sent: int = 0
    delivered: int = 0
    read: int = 0
    failed: int = 0
    dead_letter: int = 0
    manual_review: int = 0
    cancelled: int = 0


class NotificationOverviewResponse(BaseModel):
    capabilities: NotificationOverviewCapabilityCounts
    rules: NotificationOverviewRuleCounts
    recipients: NotificationOverviewRecipientCounts
    deliveries: NotificationOverviewDeliveryCounts


class NotificationCatalogResponse(BaseModel):
    event_types: list[str]
    capability_keys: list[str]
    channels: list[str]
    action_types: list[str]
    recipient_strategies: list[str]
    schedule_modes: list[str]
    condition_operators: list[str]
    variable_sources: list[str]
    variable_formats: list[str]


class NotificationCapabilityItem(BaseModel):
    capability_key: str
    enabled: bool
    updated_at: Optional[datetime] = None


class NotificationCapabilityUpdateRequest(BaseModel):
    enabled: bool


class NotificationRuleItem(BaseModel):
    id: str
    name: str
    capability_key: str
    event_type: str
    channel: str
    action_type: str
    template_key: Optional[str] = None
    recipient_strategy: str
    recipient_group_key: Optional[str] = None
    conditions_json: list = Field(default_factory=list)
    variable_mapping_json: dict = Field(default_factory=dict)
    schedule_mode: str
    schedule_offset_minutes: int
    priority: int
    enabled: bool
    configuration_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class NotificationRuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    capability_key: str = Field(..., min_length=1, max_length=80)
    event_type: str = Field(..., min_length=1, max_length=120)
    template_key: str = Field(..., min_length=1, max_length=120)
    recipient_strategy: str = Field(..., min_length=1, max_length=40)
    recipient_group_key: Optional[str] = Field(None, max_length=80)
    conditions_json: list = Field(default_factory=list)
    variable_mapping_json: dict = Field(default_factory=dict)
    schedule_mode: str = "immediate"
    schedule_offset_minutes: int = 0
    priority: int = 100
    enabled: bool = True


class NotificationRuleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    capability_key: Optional[str] = Field(None, min_length=1, max_length=80)
    event_type: Optional[str] = Field(None, min_length=1, max_length=120)
    template_key: Optional[str] = Field(None, min_length=1, max_length=120)
    recipient_strategy: Optional[str] = Field(None, min_length=1, max_length=40)
    recipient_group_key: Optional[str] = Field(None, max_length=80)
    conditions_json: Optional[list] = None
    variable_mapping_json: Optional[dict] = None
    schedule_mode: Optional[str] = None
    schedule_offset_minutes: Optional[int] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class NotificationRuleEnabledUpdateRequest(BaseModel):
    enabled: bool


class NotificationRecipientItem(BaseModel):
    id: str
    group_key: str
    name: str
    channel: str
    destination_masked: str
    status: str
    created_at: datetime
    updated_at: datetime


class NotificationRecipientCreateRequest(BaseModel):
    group_key: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=160)
    channel: str = "whatsapp"
    destination: str = Field(..., min_length=1, max_length=255)
    status: str = "active"


class NotificationRecipientUpdateRequest(BaseModel):
    group_key: Optional[str] = Field(None, min_length=1, max_length=80)
    name: Optional[str] = Field(None, min_length=1, max_length=160)
    destination: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = None


class NotificationDeliveryItem(BaseModel):
    id: str
    rule_id: str
    rule_name: Optional[str] = None
    event_type: Optional[str] = None
    channel: str
    recipient_masked: str
    template_key: Optional[str] = None
    status: str
    scheduled_for: datetime
    attempts: int
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class NotificationDeliveryListResponse(BaseModel):
    items: list[NotificationDeliveryItem]
    page: int
    page_size: int
    total: int
    pages: int
