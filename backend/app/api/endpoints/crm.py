from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.auth.deps import AuthContext, get_current_auth_context, require_roles
from app.db.session import get_db
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask

from app.schemas.crm import (
    ActivitySchema,
    ContactBriefSchema,
    CrmMetricsResponse,
    CrmSummaryResponse,
    LeadDetailResponse,
    LeadListItem,
    LeadStageCount,
    LeadUpdateRequest,
    LeadsListResponse,
    NoteCreateRequest,
    PipelineBoardResponse,
    PipelineBoardLeadItem,
    PipelineStageLeads,
    PipelineStageSchema,
    StageUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
    CrmDashboardResponse,
    EmailActionRequest,
    EmailActionResponse,
)
from app.services.crm_pipeline_service import CrmPipelineService
from app.services.crm_lead_service import CrmLeadService
from app.services.crm_activity_service import CrmActivityService
from app.services.crm_task_service import CrmTaskService
from app.services.crm_metrics_service import CrmMetricsService
from app.services.crm_query_service import CrmQueryService
from app.services.crm_dashboard_metrics_service import CrmDashboardMetricsService
from app.services.email_send_service import EmailSendService

router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])


# --- Pipeline ---

@router.get("/pipeline", response_model=List[PipelineStageSchema])
def get_crm_pipeline(
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    pipeline_service = CrmPipelineService(db)
    stages = pipeline_service.ensure_default_pipeline(context.tenant.id)
    return stages


# --- Summary ---

@router.get("/summary", response_model=CrmSummaryResponse)
def get_crm_summary(
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    pipeline_service = CrmPipelineService(db)
    stages = pipeline_service.ensure_default_pipeline(tenant_id)

    total_leads = db.scalar(
        select(func.count()).select_from(CrmLead).where(CrmLead.tenant_id == tenant_id)
    ) or 0

    total_contacts = db.scalar(
        select(func.count()).select_from(CrmContact).where(CrmContact.tenant_id == tenant_id)
    ) or 0

    counts = db.execute(
        select(CrmLead.current_stage_id, func.count())
        .where(CrmLead.tenant_id == tenant_id)
        .group_by(CrmLead.current_stage_id)
    ).all()

    count_map = {stage_id: count for stage_id, count in counts}

    leads_by_stage = [
        LeadStageCount(
            stage_key=stage.key,
            stage_name=stage.name,
            count=count_map.get(stage.id, 0),
        )
        for stage in stages
    ]

    return CrmSummaryResponse(
        total_leads=total_leads,
        total_contacts=total_contacts,
        leads_by_stage=leads_by_stage,
    )


# --- Advanced Lead Listing ---

@router.get("/leads", response_model=LeadsListResponse)
def get_crm_leads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    stage_key: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    assigned_agent_id: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    has_phone: Optional[bool] = Query(default=None),
    has_email: Optional[bool] = Query(default=None),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc"),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    query_service = CrmQueryService(db)

    items, total, _, ps, total_pages, filters_applied = query_service.list_leads(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        stage_key=stage_key,
        status=status,
        search=search,
        source=source,
        campaign=campaign,
        assigned_agent_id=assigned_agent_id,
        date_from=date_from,
        date_to=date_to,
        has_phone=has_phone,
        has_email=has_email,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return LeadsListResponse(
        items=[LeadListItem(**item) for item in items],
        total=total,
        page=page,
        page_size=ps,
        total_pages=total_pages,
        filters_applied=filters_applied,
    )


# --- Lead Detail ---

@router.get("/leads/{lead_id}", response_model=LeadDetailResponse)
def get_crm_lead_detail(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id

    lead = db.scalar(
        select(CrmLead)
        .options(
            joinedload(CrmLead.contact),
            joinedload(CrmLead.stage),
            joinedload(CrmLead.activities),
            joinedload(CrmLead.tasks),
        )
        .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
    )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    lead.activities.sort(key=lambda a: a.occurred_at or datetime.min, reverse=True)

    return LeadDetailResponse(
        id=lead.id,
        status=lead.status,
        lead_score=lead.lead_score,
        interest=lead.interest,
        industry=lead.industry,
        use_case=lead.use_case,
        volume=lead.volume,
        pain_point=lead.pain_point,
        budget_range=lead.budget_range,
        intent_level=lead.intent_level,
        next_action=lead.next_action,
        short_summary=lead.short_summary,
        summary=lead.summary,
        source=lead.source,
        campaign=lead.campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contact=ContactBriefSchema.model_validate(lead.contact),
        stage=PipelineStageSchema.model_validate(lead.stage),
        activities=[ActivitySchema.model_validate(a) for a in lead.activities],
        tasks=[TaskResponse.model_validate(t) for t in lead.tasks],
    )


# --- Lead Update ---

@router.patch("/leads/{lead_id}", response_model=LeadDetailResponse)
def update_crm_lead(
    lead_id: str,
    body: LeadUpdateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)

    update_kwargs = body.model_dump(exclude_none=True)
    if not update_kwargs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    try:
        lead = lead_service.update_lead(tenant_id, lead_id, **update_kwargs)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Reload with relationships
    db.refresh(lead)
    lead = db.scalar(
        select(CrmLead)
        .options(
            joinedload(CrmLead.contact),
            joinedload(CrmLead.stage),
            joinedload(CrmLead.activities),
            joinedload(CrmLead.tasks),
        )
        .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
    )

    lead.activities.sort(key=lambda a: a.occurred_at or datetime.min, reverse=True)

    return LeadDetailResponse(
        id=lead.id,
        status=lead.status,
        lead_score=lead.lead_score,
        interest=lead.interest,
        industry=lead.industry,
        use_case=lead.use_case,
        volume=lead.volume,
        pain_point=lead.pain_point,
        budget_range=lead.budget_range,
        intent_level=lead.intent_level,
        next_action=lead.next_action,
        short_summary=lead.short_summary,
        summary=lead.summary,
        source=lead.source,
        campaign=lead.campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contact=ContactBriefSchema.model_validate(lead.contact),
        stage=PipelineStageSchema.model_validate(lead.stage),
        activities=[ActivitySchema.model_validate(a) for a in lead.activities],
        tasks=[TaskResponse.model_validate(t) for t in lead.tasks],
    )


# --- Stage Change ---

@router.patch("/leads/{lead_id}/stage", response_model=LeadDetailResponse)
def change_lead_stage(
    lead_id: str,
    body: StageUpdateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)

    try:
        lead = lead_service.change_stage(
            tenant_id=tenant_id,
            lead_id=lead_id,
            stage_key=body.stage_key,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    db.refresh(lead)
    lead = db.scalar(
        select(CrmLead)
        .options(
            joinedload(CrmLead.contact),
            joinedload(CrmLead.stage),
            joinedload(CrmLead.activities),
            joinedload(CrmLead.tasks),
        )
        .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
    )

    lead.activities.sort(key=lambda a: a.occurred_at or datetime.min, reverse=True)

    return LeadDetailResponse(
        id=lead.id,
        status=lead.status,
        lead_score=lead.lead_score,
        interest=lead.interest,
        industry=lead.industry,
        use_case=lead.use_case,
        volume=lead.volume,
        pain_point=lead.pain_point,
        budget_range=lead.budget_range,
        intent_level=lead.intent_level,
        next_action=lead.next_action,
        short_summary=lead.short_summary,
        summary=lead.summary,
        source=lead.source,
        campaign=lead.campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contact=ContactBriefSchema.model_validate(lead.contact),
        stage=PipelineStageSchema.model_validate(lead.stage),
        activities=[ActivitySchema.model_validate(a) for a in lead.activities],
        tasks=[TaskResponse.model_validate(t) for t in lead.tasks],
    )



# --- Outbound Actions ---

def _get_action_lead_or_404(db: Session, tenant_id: str, lead_id: str) -> CrmLead:
    lead_service = CrmLeadService(db)
    lead = lead_service.get_lead_by_id(tenant_id, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _require_contact_phone(lead: CrmLead, detail: str) -> None:
    if not lead.contact or not (lead.contact.phone or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


def _require_contact_email(lead: CrmLead) -> None:
    if not lead.contact or not (lead.contact.email or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead does not have an email address.",
        )


def _require_contact_name(lead: CrmLead) -> None:
    contact_name = (lead.contact.name or "").strip() if lead.contact else ""
    if not contact_name or contact_name.lower() == "lead sin nombre":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lead does not have a contact name.",
        )


@router.post("/leads/{lead_id}/actions/whatsapp", response_model=dict)
def lead_action_whatsapp(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)
    _require_contact_phone(lead, "Lead does not have a phone number for WhatsApp.")

    # Log action request activity
    lead_service.activity_service.create_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="whatsapp_action_requested",
        title="WhatsApp enviado (Intento)",
        description="El usuario intentó enviar un mensaje de WhatsApp desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="WhatsApp integration is not configured for this tenant. Please contact support to set up Twilio/Meta API.",
    )


@router.post("/leads/{lead_id}/actions/call", response_model=dict)
def lead_action_call(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)
    _require_contact_phone(lead, "Lead does not have a phone number for outbound call.")

    # Log action request activity
    lead_service.activity_service.create_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="call_requested",
        title="Llamada saliente iniciada (Intento)",
        description="El usuario intentó iniciar una llamada saliente al contacto desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="VoIP/SIP Trunk integration is not configured for this tenant. Please contact support.",
    )


@router.post("/leads/{lead_id}/actions/schedule", response_model=dict)
def lead_action_schedule(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)
    _require_contact_name(lead)

    # Log action request activity
    lead_service.activity_service.create_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="schedule_requested",
        title="Agendamiento de reunión (Intento)",
        description="El usuario intentó agendar una reunión desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Cal.com/Google Calendar integration is not configured for this tenant. Please connect your calendar in settings.",
    )


@router.post("/leads/{lead_id}/actions/chatwoot", response_model=dict)
def lead_action_chatwoot(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)
    lead = _get_action_lead_or_404(db, tenant_id, lead_id)

    lead_service.activity_service.create_activity(
        tenant_id=tenant_id,
        lead_id=lead.id,
        contact_id=lead.contact_id,
        activity_type="chatwoot_action_requested",
        title="Apertura Chatwoot solicitada",
        description="El usuario intento abrir o asociar una conversacion de Chatwoot desde el CRM.",
    )

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Chatwoot integration is not configured or this lead has no associated Chatwoot conversation.",
    )


@router.post("/leads/{lead_id}/actions/email", response_model=EmailActionResponse)
def lead_action_email(
    lead_id: str,
    body: EmailActionRequest | None = None,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    body = body or EmailActionRequest()
    service = EmailSendService(db)
    try:
        if body.preview_only:
            result = service.preview_lead_email(
                tenant_id=tenant_id,
                lead_id=lead_id,
                template_key=body.template_key,
                subject=body.subject,
                message=body.message,
                content_format=body.content_format,
                content=body.content,
                asset_ids=body.asset_ids,
                form_token_ids=body.form_token_ids,
            )
        else:
            result = service.send_lead_email(
                tenant_id=tenant_id,
                lead_id=lead_id,
                template_key=body.template_key,
                subject=body.subject,
                message=body.message,
                content_format=body.content_format,
                content=body.content,
                asset_ids=body.asset_ids,
                form_token_ids=body.form_token_ids,
            )
    except ValueError as exc:
        code = status.HTTP_404_NOT_FOUND if str(exc) == "Lead not found" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.error_message or "Email send failed.")
    return EmailActionResponse(
        status=result.status,
        email_send_id=result.email_send_id,
        provider_email_id=result.provider_email_id,
        preview=result.preview,
    )


# --- Pipeline Board ---

@router.get("/pipeline/board", response_model=PipelineBoardResponse)
def get_pipeline_board(
    limit_per_stage: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    assigned_agent_id: Optional[str] = Query(default=None),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    query_service = CrmQueryService(db)

    board = query_service.get_pipeline_board(
        tenant_id=tenant_id,
        limit_per_stage=limit_per_stage,
        search=search,
        status=status,
        source=source,
        campaign=campaign,
        assigned_agent_id=assigned_agent_id,
    )

    return PipelineBoardResponse(
        stages=[PipelineStageLeads(**stage) for stage in board]
    )


# --- Activities ---

@router.get("/activities", response_model=List[ActivitySchema])
def get_crm_activities(
    lead_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None),
    activity_type: Optional[str] = Query(default=None),
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    activity_service = CrmActivityService(db)

    activities = activity_service.get_activities(
        tenant_id=tenant_id,
        lead_id=lead_id,
        contact_id=contact_id,
        activity_type=activity_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=(page - 1) * limit,
    )

    return [ActivitySchema.model_validate(a) for a in activities]


# --- Notes ---

@router.post("/leads/{lead_id}/notes", response_model=LeadDetailResponse)
def create_lead_note(
    lead_id: str,
    body: NoteCreateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)

    lead = lead_service.add_note(
        tenant_id=tenant_id,
        lead_id=lead_id,
        note=body.note,
    )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    db.refresh(lead)
    lead = db.scalar(
        select(CrmLead)
        .options(
            joinedload(CrmLead.contact),
            joinedload(CrmLead.stage),
            joinedload(CrmLead.activities),
            joinedload(CrmLead.tasks),
        )
        .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
    )

    lead.activities.sort(key=lambda a: a.occurred_at or datetime.min, reverse=True)

    return LeadDetailResponse(
        id=lead.id,
        status=lead.status,
        lead_score=lead.lead_score,
        interest=lead.interest,
        industry=lead.industry,
        use_case=lead.use_case,
        volume=lead.volume,
        pain_point=lead.pain_point,
        budget_range=lead.budget_range,
        intent_level=lead.intent_level,
        next_action=lead.next_action,
        short_summary=lead.short_summary,
        summary=lead.summary,
        source=lead.source,
        campaign=lead.campaign,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        contact=ContactBriefSchema.model_validate(lead.contact),
        stage=PipelineStageSchema.model_validate(lead.stage),
        activities=[ActivitySchema.model_validate(a) for a in lead.activities],
        tasks=[TaskResponse.model_validate(t) for t in lead.tasks],
    )


# --- Tasks ---

@router.get("/tasks", response_model=List[TaskResponse])
def list_crm_tasks(
    lead_id: Optional[str] = Query(default=None),
    contact_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    task_service = CrmTaskService(db)

    tasks = task_service.list_tasks(
        tenant_id=tenant_id,
        lead_id=lead_id,
        contact_id=contact_id,
        status=status,
        priority=priority,
    )

    return [TaskResponse.model_validate(t) for t in tasks]


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_crm_task(
    body: TaskCreateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    task_service = CrmTaskService(db)

    try:
        task = task_service.create_task(
            tenant_id=tenant_id,
            title=body.title,
            lead_id=body.lead_id,
            contact_id=body.contact_id,
            description=body.description,
            due_at=body.due_at,
            priority=body.priority,
            assigned_to_user_id=body.assigned_to_user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    return TaskResponse.model_validate(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_crm_task(
    task_id: str,
    body: TaskUpdateRequest,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    task_service = CrmTaskService(db)

    update_kwargs = body.model_dump(exclude_none=True)
    if not update_kwargs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    try:
        task = task_service.update_task(tenant_id, task_id, **update_kwargs)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return TaskResponse.model_validate(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crm_task(
    task_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> None:
    tenant_id = context.tenant.id
    task_service = CrmTaskService(db)

    deleted = task_service.delete_task(tenant_id, task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )


# --- Metrics ---

@router.get("/metrics", response_model=CrmMetricsResponse)
def get_crm_metrics(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    source: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    assigned_agent_id: Optional[str] = Query(default=None),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    metrics_service = CrmMetricsService(db)

    metrics = metrics_service.get_metrics(
        tenant_id=tenant_id,
        date_from=date_from,
        date_to=date_to,
        source=source,
        campaign=campaign,
        assigned_agent_id=assigned_agent_id,
    )

    return CrmMetricsResponse(**metrics)


# --- Leads Deletion ---

@router.delete("/leads/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_crm_lead(
    lead_id: str,
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin"])),
    db: Session = Depends(get_db),
) -> None:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)

    deleted = lead_service.delete_lead(tenant_id, lead_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )


@router.delete("/leads", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_crm_leads(
    context: AuthContext = Depends(require_roles(["platform_admin"])),
    db: Session = Depends(get_db),
) -> None:
    tenant_id = context.tenant.id
    lead_service = CrmLeadService(db)

    lead_service.delete_all_leads(tenant_id)


# --- Dashboard ---

@router.get("/dashboard", response_model=CrmDashboardResponse)
def get_crm_dashboard(
    range: Optional[str] = Query(default="30d"),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    source: Optional[str] = Query(default=None),
    campaign: Optional[str] = Query(default=None),
    context: AuthContext = Depends(require_roles(["platform_admin", "tenant_admin", "tenant_analyst", "tenant_viewer"])),
    db: Session = Depends(get_db),
) -> Any:
    if range == "custom" and (not date_from or not date_to):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range=custom requires both date_from and date_to parameters",
        )

    metrics_service = CrmDashboardMetricsService(db)
    dashboard_data = metrics_service.get_dashboard(
        tenant=context.tenant,
        range_val=range,
        date_from_str=date_from,
        date_to_str=date_to,
        source=source,
        campaign=campaign,
    )
    return dashboard_data


