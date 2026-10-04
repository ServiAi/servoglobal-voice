from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- Pipeline ---

class CallSummaryResponse(BaseModel):
    status: str
    summary: Optional[str] = None
    short_summary: Optional[str] = None
    call_date: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    source: Optional[str] = None


class CallSummaryAssetRequest(BaseModel):
    format: str = Field(default="md", pattern="^(md|txt)$")


class CallSummaryAssetResponse(BaseModel):
    asset_id: str
    filename: str
    mime_type: str
    file_size_bytes: int


class WhatsAppActionRequest(BaseModel):
    template_key: str = Field(default="lead_follow_up", min_length=1, max_length=80)
    message: Optional[str] = None
    variables: dict[str, Any] = Field(default_factory=dict)
    preview_only: bool = False


class WhatsAppActionResponse(BaseModel):
    status: str
    whatsapp_message_id: Optional[str] = None
    provider_message_id: Optional[str] = None
    preview: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class WhatsAppMessageResponse(BaseModel):
    id: str
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    template_key: Optional[str] = None
    provider_message_id: Optional[str] = None
    direction: str
    to_phone: Optional[str] = None
    from_phone: Optional[str] = None
    message_preview: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallSummaryInsertedRequest(BaseModel):
    variant: str = "full"


class BookingCreateRequest(BaseModel):
    start: str
    timezone: str = "America/Bogota"
    event_type_id: Optional[int] = None
    event_type_slug: Optional[str] = None
    username: Optional[str] = None
    team_slug: Optional[str] = None
    organization_slug: Optional[str] = None
    attendee_name: str = Field(..., min_length=1, max_length=255)
    attendee_email: str = Field(..., min_length=3, max_length=255)
    attendee_phone: Optional[str] = Field(None, max_length=80)
    booking_fields_responses: dict[str, Any] = Field(default_factory=dict)
    scheduling_resource_id: Optional[str] = None
    scheduling_team_id: Optional[str] = None
    notes: Optional[str] = None


class BookingCancelRequest(BaseModel):
    reason: Optional[str] = None


class BookingRescheduleRequest(BaseModel):
    new_start_time: str
    new_end_time: str


class BookingResponse(BaseModel):
    id: str
    provider: str
    provider_booking_id: Optional[str] = None
    provider_booking_uid: Optional[str] = None
    status: str
    start_at: datetime
    end_at: Optional[datetime] = None
    timezone: str
    duration_minutes: Optional[int] = None
    meeting_url: Optional[str] = None
    attendee_name: str
    attendee_email: str
    attendee_phone: Optional[str] = None
    calendar_mode: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VoiceAvailabilityRequest(BaseModel):
    call_context_id: Optional[str] = None
    agent_id: Optional[str] = None
    did: Optional[str] = None
    date: str
    jornada: Optional[str] = None
    reference_datetime: Optional[str] = None


class VoiceBookingRequest(BaseModel):
    call_context_id: Optional[str] = None
    agent_id: Optional[str] = None
    did: Optional[str] = None
    start: str
    attendee_name: str
    attendee_email: str
    attendee_phone: Optional[str] = None


class VoiceHandoffRequest(BaseModel):
    call_context_id: Optional[str] = None
    agent_id: Optional[str] = None
    did: Optional[str] = None
    reason: Optional[str] = None


class DashboardPeriod(BaseModel):
    from_date: str = Field(..., alias="from")
    to: str
    range: str

    model_config = ConfigDict(populate_by_name=True)


class CrmDashboardKpis(BaseModel):
    total_leads: int
    new_leads: int
    contacted_leads: int
    connected_leads: int
    qualified_leads: int
    scheduled_leads: int
    voicemail_leads: int
    follow_up_leads: int
    not_interested_leads: int
    won_leads: int
    lost_leads: int
    open_leads: int
    pending_tasks: int
    overdue_tasks: int
    leads_with_next_action: int


class CrmDashboardConversion(BaseModel):
    contact_rate: float
    connection_rate: float
    qualification_rate: float
    schedule_rate: float
    win_rate: float


class CrmDashboardFunnelItem(BaseModel):
    stage: str
    label: str
    count: int


class CrmDashboardSourceItem(BaseModel):
    source: str
    total_leads: int
    qualified_leads: int
    scheduled_leads: int
    won_leads: int
    conversion_rate: float


class CrmDashboardCampaignItem(BaseModel):
    campaign: str
    total_leads: int
    qualified_leads: int
    scheduled_leads: int
    won_leads: int
    conversion_rate: float


class CrmDashboardCallMetrics(BaseModel):
    total_calls: int
    answered_calls: int
    unanswered_calls: int
    voicemail_calls: int
    failed_calls: int
    average_duration_seconds: float
    total_billed_minutes: float


class CrmVoiceCapacityEvent(BaseModel):
    event_type: Literal["capacity_reached", "reconciled", "forced_release"]
    occurred_at: datetime
    active_calls: Optional[int] = None
    max_concurrent_calls: Optional[int] = None
    resulting_status: Optional[str] = None


class CrmVoiceCapacityMetrics(BaseModel):
    configured: bool
    route_status: Optional[str] = None
    provision_status: Optional[str] = None
    active_calls: int
    max_concurrent_calls: int
    available_slots: int
    utilization_percent: float
    capacity_rejections: int
    reconciled_calls: int
    forced_releases: int
    recent_events: List[CrmVoiceCapacityEvent]


class CrmPendingActionItem(BaseModel):
    lead_id: str
    contact_name: str
    stage: str
    next_action: Optional[str] = None
    source: Optional[str] = None
    campaign: Optional[str] = None
    updated_at: datetime


class CrmDashboardResponse(BaseModel):
    period: DashboardPeriod
    kpis: CrmDashboardKpis
    conversion: CrmDashboardConversion
    funnel: List[CrmDashboardFunnelItem]
    sources: List[CrmDashboardSourceItem]
    campaigns: List[CrmDashboardCampaignItem]
    calls: CrmDashboardCallMetrics
    voice_capacity: CrmVoiceCapacityMetrics
    pending_actions: List[CrmPendingActionItem]
