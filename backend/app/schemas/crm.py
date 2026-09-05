from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.integrations import (
    EmailActionRequest,
    EmailActionResponse,
    VoiceCallActionRequest,
    VoiceCallActionResponse,
    VoiceCallResponse,
)


# --- Pipeline ---

class PipelineStageSchema(BaseModel):
    id: str
    key: str
    name: str
    position: int
    is_default: bool
    is_terminal: bool

    model_config = ConfigDict(from_attributes=True)


# --- Contact ---

class ContactBriefSchema(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# --- Lead ---

class LeadStageCount(BaseModel):
    stage_key: str
    stage_name: str
    count: int


class LeadListItem(BaseModel):
    lead_id: str
    contact_name: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    company: Optional[str] = None
    stage_key: str
    stage_name: str
    status: str
    lead_score: Optional[int] = None
    interest: Optional[str] = None
    use_case: Optional[str] = None
    source: Optional[str] = None
    campaign: Optional[str] = None
    short_summary: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    last_call_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LeadBriefSchema(BaseModel):
    id: str
    status: str
    lead_score: Optional[int] = None
    interest: Optional[str] = None
    use_case: Optional[str] = None
    short_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    contact: ContactBriefSchema
    stage: PipelineStageSchema

    model_config = ConfigDict(from_attributes=True)


class LeadsListResponse(BaseModel):
    items: List[LeadListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters_applied: dict


class ActivitySchema(BaseModel):
    id: str
    activity_type: str
    title: str
    description: Optional[str] = None
    outcome: Optional[str] = None
    occurred_at: datetime
    call_id: Optional[str] = None

    provider_event: Optional[str] = None
    recording_url: Optional[str] = None
    summary: Optional[str] = None
    short_summary: Optional[str] = None
    normalized_status: Optional[str] = None
    duration_seconds: Optional[float] = None
    billed_minutes: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        def _to_float(v):
            try:
                return float(v) if v is not None else None
            except (ValueError, TypeError):
                return None

        if isinstance(data, dict):
            payload = data.get("payload_json") or {}
            call_obj = payload.get("call") or {}

            data["provider_event"] = payload.get("event") or payload.get("event_type") or payload.get("eventType")
            data["recording_url"] = call_obj.get("recordingUrl") or call_obj.get("recording_url") or payload.get("recordingUrl")
            data["summary"] = call_obj.get("summary") or payload.get("summary")
            data["short_summary"] = call_obj.get("shortSummary") or call_obj.get("short_summary") or payload.get("shortSummary")
            data["normalized_status"] = call_obj.get("status") or call_obj.get("normalizedStatus") or call_obj.get("normalized_status") or payload.get("status")
            data["duration_seconds"] = _to_float(call_obj.get("durationSeconds") or call_obj.get("duration") or call_obj.get("duration_seconds"))
            data["billed_minutes"] = _to_float(call_obj.get("billedMinutes") or call_obj.get("billedDuration") or call_obj.get("billed_minutes"))

            if "payload_json" in data:
                del data["payload_json"]
        else:
            payload = getattr(data, "payload_json", {}) or {}
            call_obj = payload.get("call") or {}

            return {
                "id": getattr(data, "id", None),
                "activity_type": getattr(data, "activity_type", None),
                "title": getattr(data, "title", None),
                "description": getattr(data, "description", None),
                "outcome": getattr(data, "outcome", None),
                "occurred_at": getattr(data, "occurred_at", None),
                "call_id": getattr(data, "call_id", None),
                "provider_event": payload.get("event") or payload.get("event_type") or payload.get("eventType"),
                "recording_url": call_obj.get("recordingUrl") or call_obj.get("recording_url") or payload.get("recordingUrl"),
                "summary": call_obj.get("summary") or payload.get("summary"),
                "short_summary": call_obj.get("shortSummary") or call_obj.get("short_summary") or payload.get("shortSummary"),
                "normalized_status": call_obj.get("status") or call_obj.get("normalizedStatus") or call_obj.get("normalized_status") or payload.get("status"),
                "duration_seconds": _to_float(call_obj.get("durationSeconds") or call_obj.get("duration") or call_obj.get("duration_seconds")),
                "billed_minutes": _to_float(call_obj.get("billedMinutes") or call_obj.get("billedDuration") or call_obj.get("billed_minutes")),
            }
        return data


class TaskResponse(BaseModel):
    id: str
    tenant_id: str
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    assigned_to_user_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskCreateRequest(BaseModel):
    lead_id: Optional[str] = None
    contact_id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: str = "medium"
    assigned_to_user_id: Optional[str] = None


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to_user_id: Optional[str] = None


class LeadUpdateRequest(BaseModel):
    interest: Optional[str] = None
    industry: Optional[str] = None
    use_case: Optional[str] = None
    volume: Optional[str] = None
    pain_point: Optional[str] = None
    budget_range: Optional[str] = None
    intent_level: Optional[str] = None
    next_action: Optional[str] = None
    lead_score: Optional[int] = Field(None, ge=0, le=100)
    status: Optional[str] = None
    source: Optional[str] = None
    campaign: Optional[str] = None


class StageUpdateRequest(BaseModel):
    stage_key: str = Field(..., min_length=1)
    reason: Optional[str] = None


class NoteCreateRequest(BaseModel):
    note: str = Field(..., min_length=1)


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


class LeadDetailResponse(BaseModel):
    id: str
    status: str
    lead_score: Optional[int] = None
    interest: Optional[str] = None
    industry: Optional[str] = None
    use_case: Optional[str] = None
    volume: Optional[str] = None
    pain_point: Optional[str] = None
    budget_range: Optional[str] = None
    intent_level: Optional[str] = None
    next_action: Optional[str] = None
    short_summary: Optional[str] = None
    summary: Optional[str] = None
    source: Optional[str] = None
    campaign: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    contact: ContactBriefSchema
    stage: PipelineStageSchema
    activities: List[ActivitySchema]
    tasks: List[TaskResponse]

    model_config = ConfigDict(from_attributes=True)


class CrmSummaryResponse(BaseModel):
    total_leads: int
    total_contacts: int
    leads_by_stage: List[LeadStageCount]


# --- Pipeline Board ---

class PipelineBoardLeadItem(BaseModel):
    id: str
    contact_name: str
    phone: Optional[str] = None
    company: Optional[str] = None
    short_summary: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    status: str


class PipelineStageLeads(BaseModel):
    id: str
    key: str
    name: str
    position: int
    count: int
    leads: List[PipelineBoardLeadItem]


class PipelineBoardResponse(BaseModel):
    stages: List[PipelineStageLeads]


# --- Metrics ---

class LeadsByStageMetric(BaseModel):
    stage_key: str
    stage_name: str
    count: int


class LeadsBySourceMetric(BaseModel):
    source: str
    count: int


class LeadsByCampaignMetric(BaseModel):
    campaign: str
    count: int


class CrmMetricsResponse(BaseModel):
    total_contacts: int
    total_leads: int
    open_leads: int
    won_leads: int
    lost_leads: int
    unqualified_leads: int
    leads_by_stage: List[LeadsByStageMetric]
    leads_by_source: List[LeadsBySourceMetric]
    leads_by_campaign: List[LeadsByCampaignMetric]
    leads_created_today: int
    leads_created_this_week: int
    leads_created_this_month: int
    scheduled_leads: int
    voicemail_leads: int
    follow_up_leads: int
    pending_tasks: int
    overdue_tasks: int
    conversion_rate: float
    contact_completion_rate: float


# --- Dashboard Commercial ---

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

