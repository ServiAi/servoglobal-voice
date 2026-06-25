from __future__ import annotations

from datetime import datetime
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmActivity, CrmCallContext, CrmContact, CrmLead, CrmPipelineStage

ALLOWED_SORT_FIELDS = {"created_at", "updated_at", "last_activity_at", "stage", "contact_name", "lead_score"}


class CrmQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _lead_context(self, lead: CrmLead) -> CrmCallContext | None:
        filters = []
        if lead.context_id:
            filters.append(CrmCallContext.context_id == lead.context_id)
        if lead.form_submission_id:
            filters.append(CrmCallContext.form_submission_id == lead.form_submission_id)
        if not filters:
            return None

        return self.db.scalar(
            select(CrmCallContext)
            .where(CrmCallContext.tenant_id == lead.tenant_id, or_(*filters))
            .order_by(CrmCallContext.created_at.desc())
            .limit(1)
        )

    def _display_contact(self, lead: CrmLead) -> dict[str, str | None]:
        contact = lead.contact
        context = self._lead_context(lead)
        return {
            "name": (context.name if context and context.name else None) or contact.name,
            "phone": (context.phone if context and context.phone else None) or contact.phone,
            "email": (context.email if context and context.email else None) or contact.email,
            "company": (context.company if context and context.company else None) or contact.company,
        }

    def _ensure_contact_joined(self, query, already_joined: bool) -> tuple:
        if not already_joined:
            return query.join(CrmLead.contact), True
        return query, True

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

        contact_joined = False

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
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            base_query = base_query.where(
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
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            base_query = base_query.where(CrmContact.phone.isnot(None))
        elif has_phone is False:
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            base_query = base_query.where(CrmContact.phone.is_(None))

        if has_email is True:
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            base_query = base_query.where(CrmContact.email.isnot(None))
        elif has_email is False:
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            base_query = base_query.where(CrmContact.email.is_(None))

        # Count
        count_query = select(func.count()).select_from(base_query.subquery())
        total = self.db.scalar(count_query) or 0

        # Sorting
        if sort_by == "contact_name":
            base_query, contact_joined = self._ensure_contact_joined(base_query, contact_joined)
            order_col = CrmContact.name
        elif sort_by == "stage":
            base_query = base_query.join(CrmLead.stage)
            order_col = CrmPipelineStage.position
        elif sort_by == "last_activity_at":
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
            stage = lead.stage
            display_contact = self._display_contact(lead)

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
                "contact_name": display_contact["name"],
                "contact_phone": display_contact["phone"],
                "contact_email": display_contact["email"],
                "company": display_contact["company"],
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
                "lead_score": lead.lead_score,
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
            base_where = [
                CrmLead.tenant_id == tenant_id,
                CrmLead.current_stage_id == stage.id,
            ]

            if status:
                base_where.append(CrmLead.status == status)
            if source:
                base_where.append(CrmLead.source == source)
            if campaign:
                base_where.append(CrmLead.campaign == campaign)
            if assigned_agent_id:
                base_where.append(CrmLead.owner_agent_id == assigned_agent_id)

            # Real count before limit
            count_query = select(func.count()).select_from(CrmLead).where(*base_where)

            if search:
                search_term = f"%{search}%"
                count_query = count_query.join(CrmLead.contact).where(
                    or_(
                        CrmContact.name.ilike(search_term),
                        CrmContact.phone.ilike(search_term),
                        CrmContact.email.ilike(search_term),
                        CrmContact.company.ilike(search_term),
                        CrmLead.short_summary.ilike(search_term),
                    )
                )

            real_count = self.db.scalar(count_query) or 0

            # Fetch limited leads
            fetch_query = (
                select(CrmLead)
                .options(joinedload(CrmLead.contact))
                .where(*base_where)
            )

            if search:
                search_term = f"%{search}%"
                fetch_query = fetch_query.join(CrmLead.contact).where(
                    or_(
                        CrmContact.name.ilike(search_term),
                        CrmContact.phone.ilike(search_term),
                        CrmContact.email.ilike(search_term),
                        CrmContact.company.ilike(search_term),
                        CrmLead.short_summary.ilike(search_term),
                    )
                )

            fetch_query = fetch_query.order_by(CrmLead.updated_at.desc()).limit(limit_per_stage)
            leads = self.db.scalars(fetch_query).unique().all()

            stage_leads = []
            for lead in leads:
                display_contact = self._display_contact(lead)
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
                    "contact_name": display_contact["name"] or "Sin nombre",
                    "phone": display_contact["phone"],
                    "company": display_contact["company"],
                    "short_summary": lead.short_summary,
                    "last_activity_at": last_activity,
                    "status": lead.status,
                })

            board.append({
                "id": stage.id,
                "key": stage.key,
                "name": stage.name,
                "position": stage.position,
                "count": real_count,
                "leads": stage_leads,
            })

        return board
