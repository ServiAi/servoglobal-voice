from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.auth.deps import AuthContext, get_current_auth_context
from app.db.session import get_db
from app.models.crm import CrmContact, CrmPipelineStage, CrmLead, CrmActivity, CrmTask
from app.services.crm_pipeline_service import CrmPipelineService

router = APIRouter(prefix="/api/v1/crm", tags=["CRM"])

# --- Pydantic Schemas ---

class PipelineStageSchema(BaseModel):
    id: str
    key: str
    name: str
    position: int
    is_default: bool
    is_terminal: bool

    model_config = ConfigDict(from_attributes=True)

class LeadStageCount(BaseModel):
    stage_key: str
    stage_name: str
    count: int

class CrmSummaryResponse(BaseModel):
    total_leads: int
    total_contacts: int
    leads_by_stage: List[LeadStageCount]

class ContactBriefSchema(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

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

class ActivitySchema(BaseModel):
    id: str
    activity_type: str
    title: str
    description: Optional[str] = None
    outcome: Optional[str] = None
    occurred_at: datetime
    payload_json: dict

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

class LeadsListResponse(BaseModel):
    items: List[LeadBriefSchema]
    total: int
    page: int
    page_size: int

# --- API Router Endpoints ---

@router.get("/pipeline", response_model=List[PipelineStageSchema])
def get_crm_pipeline(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    # Ensure default pipeline stages are initialized
    pipeline_service = CrmPipelineService(db)
    stages = pipeline_service.ensure_default_pipeline(context.tenant.id)
    return stages

@router.get("/summary", response_model=CrmSummaryResponse)
def get_crm_summary(
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id
    
    # Initialize pipeline if not present
    pipeline_service = CrmPipelineService(db)
    stages = pipeline_service.ensure_default_pipeline(tenant_id)

    total_leads = db.scalar(
        select(func.count()).select_from(CrmLead).where(CrmLead.tenant_id == tenant_id)
    ) or 0

    total_contacts = db.scalar(
        select(func.count()).select_from(CrmContact).where(CrmContact.tenant_id == tenant_id)
    ) or 0

    # Get leads count grouped by stage
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

@router.get("/leads", response_model=LeadsListResponse)
def get_crm_leads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id

    # Count total
    total = db.scalar(
        select(func.count()).select_from(CrmLead).where(CrmLead.tenant_id == tenant_id)
    ) or 0

    # Fetch paginated leads
    leads = db.scalars(
        select(CrmLead)
        .options(joinedload(CrmLead.contact), joinedload(CrmLead.stage))
        .where(CrmLead.tenant_id == tenant_id)
        .order_by(CrmLead.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()

    return LeadsListResponse(
        items=list(leads),
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/leads/{lead_id}", response_model=LeadDetailResponse)
def get_crm_lead_detail(
    lead_id: str,
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id

    lead = db.scalar(
        select(CrmLead)
        .options(
            joinedload(CrmLead.contact),
            joinedload(CrmLead.stage),
            joinedload(CrmLead.activities),
        )
        .where(CrmLead.tenant_id == tenant_id, CrmLead.id == lead_id)
    )

    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )

    # Sort activities by occurred_at desc
    lead.activities.sort(key=lambda a: a.occurred_at, reverse=True)

    return lead

@router.get("/activities", response_model=List[ActivitySchema])
def get_crm_activities(
    limit: int = Query(default=50, ge=1, le=100),
    context: AuthContext = Depends(get_current_auth_context),
    db: Session = Depends(get_db),
) -> Any:
    tenant_id = context.tenant.id

    activities = db.scalars(
        select(CrmActivity)
        .where(CrmActivity.tenant_id == tenant_id)
        .order_by(CrmActivity.occurred_at.desc())
        .limit(limit)
    ).all()

    return list(activities)
