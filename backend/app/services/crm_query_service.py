from __future__ import annotations

from datetime import datetime
from sqlalchemy import func, or_, select, case
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmContact, CrmLead, CrmPipelineStage, CrmActivity

ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "last_activity_at", "stage", "contact_name"}


class CrmQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_leads(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        stage_key: str | None = None,
        status: str | None = None,
        search: str | None = None,
        source: str | None = None,
        campaign: str | None = None,
        assigned_agent_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        has_phone: bool | None = None,
        has_email: bool | None = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict], int]:
        if sort_by not in ALLOWED_SORT_FIELDS:
            sort_by = "updated_at"

        base_query = (
            select(CrmLead)
            .options(
                joinedload(CrmLead.contact),
                joinedload(CrmLead.stage),
            )
            .where(CrmLead.tenant_id == tenant_id)
        )

        # Filters
        if stage_key:
            stage = self.db.scalar(
                select(CrmPipelineStage).where(
                    CrmPipelineStage.tenant_id == tenant_id,
                    CrmPipelineStage.key == stage_key,
                )
            )
            if stage:
                base_query = base_query.where(CrmLead.current_stage_id == stage.id)

        if status:
            base_query = base_query.where(CrmLead.status == status)

        if source:
            base_query = base_query.where(CrmLead.source == source)

        if campaign:
            base_query = base_query.where(CrmLead.campaign == campaign)

        if assigned_agent_id:
            base_query = base_query.where(CrmLead.owner_agent_id == assigned_agent_id)

        if date_from:
            base_query = base_query.where(CrmLead.created_at >= date_from)

        if date_to:
            base_query = base_query.where(CrmLead.created_at <= date_to)

        if search:
            search_term = f"%{search}%"
            base_query = base_query.join(CrmLead.contact).where(
                or_(
                    CrmContact.name.ilike(search_term),
                    CrmContact.phone.ilike(search_term),
                    CrmContact.email.ilike(search_term),
                    CrmContact.company.ilike(search_term),
                    CrmLead.short_summary.ilike(search_term),
                    CrmLead.interest.ilike(search_term),
                    CrmLead.use_case.ilike(search_term),
                )
            )

        if has_phone is True:
            base_query = base_query.where(CrmContact.phone.isnot(None))
        elif has_phone is False:
            base_query = base_query.where(CrmContact.phone.is_(None))

        if has_email is True:
            base_query = base_query.where(CrmContact.email.isnot(None))
        elif has_email is False:
            base_query = base_query.where(CrmContact.email.is_(None))

        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = self.db.scalar(count_query) or 0

        # Sorting
        if sort_by == "contact_name":
            base_query = base_query.join(CrmLead.contact)
            order_col = CrmContact.name
        elif sort_by == "stage":
            base_query = base_query.join(CrmLead.stage)
            order_col = CrmPipelineStage.position
        elif sort_by == "last_activity_at":
            # Subquery to get max activity date
            subq = (
                select(CrmActivity.lead_id, func.max(CrmActivity.occurred_at).label("last_at"))
                .where(CrmActivity.tenant_id == tenant_id)
                .group_by(CrmActivity.lead_id)
                .subquery()
            )
            base_query = base_query.outerjoin(subq, CrmLead.id == subq.c.lead_id)
            order_col = subq.c.last_at
        else:
            order_col = getattr(CrmLead, sort_by, CrmLead.updated_at)

        if sort_order == "asc":
            base_query = base_query.order_by(order_col.asc().nullslast())
        else:
            base_query = base_query.order_by(order_col.desc().nullslast())

        # Paginate
        leads = self.db.scalars(
            base_query.offset((page - 1) * page_size).limit(page_size)
        ).unique().all()

        result = []
        for lead in leads:
            contact = lead.contact
            stage = lead.stage

            # Get last activity
            last_activity = self.db.scalar(
                select(CrmActivity.occurred_at)
                .where(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.lead_id == lead.id,
                )
                .order_by(CrmActivity.occurred_at.desc())
                .limit(1)
            )

            result.append({
                "lead_id": lead.id,
                "contact_name": contact.name,
                "contact_phone": contact.phone,
                "contact_email": contact.email,
                "company": contact.company,
                "stage_key": stage.key,
                "stage_name": stage.name,
                "status": lead.status,
                "interest": lead.interest,
                "use_case": lead.use_case,
                "source": lead.source,
                "campaign": lead.campaign,
                "short_summary": lead.short_summary,
                "last_activity_at": last_activity,
                "last_call_id": lead.last_call_id,
                "created_at": lead.created_at,
                "updated_at": lead.updated_at,
            })

        filters_applied = {
            "stage_key": stage_key,
            "status": status,
            "search": search,
            "source": source,
            "campaign": campaign,
            "assigned_agent_id": assigned_agent_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "has_phone": has_phone,
            "has_email": has_email,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }

        total_pages = max(1, (total + page_size - 1) // page_size)

        return result, total, page, page_size, total_pages, filters_applied

    def get_pipeline_board(
        self,
        tenant_id: str,
        limit_per_stage: int = 20,
        search: str | None = None,
        status: str | None = None,
        source: str | None = None,
        campaign: str | None = None,
        assigned_agent_id: str | None = None,
    ) -> list[dict]:
        from app.services.crm_pipeline_service import CrmPipelineService
        pipeline_service = CrmPipelineService(self.db)
        stages = pipeline_service.ensure_default_pipeline(tenant_id)

        board = []
        for stage in sorted(stages, key=lambda s: s.position):
            query = (
                select(CrmLead)
                .options(joinedload(CrmLead.contact))
                .where(
                    CrmLead.tenant_id == tenant_id,
                    CrmLead.current_stage_id == stage.id,
                )
            )

            if status:
                query = query.where(CrmLead.status == status)
            if source:
                query = query.where(CrmLead.source == source)
            if campaign:
                query = query.where(CrmLead.campaign == campaign)
            if assigned_agent_id:
                query = query.where(CrmLead.owner_agent_id == assigned_agent_id)
            if search:
                search_term = f"%{search}%"
                query = query.join(CrmLead.contact).where(
                    or_(
                        CrmContact.name.ilike(search_term),
                        CrmContact.phone.ilike(search_term),
                        CrmContact.email.ilike(search_term),
                        CrmContact.company.ilike(search_term),
                        CrmLead.short_summary.ilike(search_term),
                    )
                )

            query = query.order_by(CrmLead.updated_at.desc()).limit(limit_per_stage)
            leads = self.db.scalars(query).unique().all()

            stage_leads = []
            for lead in leads:
                last_activity = self.db.scalar(
                    select(CrmActivity.occurred_at)
                    .where(
                        CrmActivity.tenant_id == tenant_id,
                        CrmActivity.lead_id == lead.id,
                    )
                    .order_by(CrmActivity.occurred_at.desc())
                    .limit(1)
                )

                stage_leads.append({
                    "id": lead.id,
                    "contact_name": lead.contact.name if lead.contact else "Sin nombre",
                    "phone": lead.contact.phone if lead.contact else None,
                    "company": lead.contact.company if lead.contact else None,
                    "short_summary": lead.short_summary,
                    "last_activity_at": last_activity,
                    "status": lead.status,
                })

            board.append({
                "id": stage.id,
                "key": stage.key,
                "name": stage.name,
                "position": stage.position,
                "count": len(stage_leads),
                "leads": stage_leads,
            })

        return board