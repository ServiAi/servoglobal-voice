"""The CRM-only part of the CRM dashboard (funnel, KPIs, breakdowns, call links,
pending-action candidates). The cross-domain composition (Analytics calls,
telephony capacity) stays outside CRM and consumes these results through
``crm.public``."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.modules.crm.application.pipeline_service import CrmPipelineService
from app.modules.crm.domain.views import CrmFunnelSnapshot, FunnelBreakdown, PendingActionCandidate
from app.modules.crm.infrastructure.models import CrmActivity, CrmCallContext, CrmLead, CrmTask


class CrmDashboardQuery:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _lead_filters(tenant_id, date_from, date_to, source, campaign):
        filters = [CrmLead.tenant_id == tenant_id]
        if date_from:
            filters.append(CrmLead.created_at >= date_from)
        if date_to:
            filters.append(CrmLead.created_at <= date_to)
        if source:
            filters.append(CrmLead.source == source)
        if campaign:
            filters.append(CrmLead.campaign == campaign)
        return filters

    def funnel(
        self,
        tenant_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
        source: str | None,
        campaign: str | None,
    ) -> CrmFunnelSnapshot:
        stages = CrmPipelineService(self.db).ensure_default_pipeline(tenant_id)
        stage_key_to_id = {s.key: s.id for s in stages}
        stage_id_to_key = {s.id: s.key for s in stages}
        lead_filters = self._lead_filters(tenant_id, date_from, date_to, source, campaign)

        counts_res = self.db.execute(
            select(CrmLead.current_stage_id, func.count()).where(*lead_filters).group_by(CrmLead.current_stage_id)
        ).all()
        counts_by_stage_id = {stage_id: cnt for stage_id, cnt in counts_res}
        stage_counts = {key: counts_by_stage_id.get(stage_id, 0) for key, stage_id in stage_key_to_id.items()}

        open_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead).where(*lead_filters, CrmLead.status == "open")
        ) or 0
        pending_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask).where(CrmTask.tenant_id == tenant_id, CrmTask.status == "pending")
        ) or 0
        now_utc = datetime.now(UTC)
        overdue_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask).where(
                CrmTask.tenant_id == tenant_id,
                CrmTask.status == "pending",
                CrmTask.due_at.isnot(None),
                CrmTask.due_at < now_utc,
            )
        ) or 0
        leads_with_next_action = self.db.scalar(
            select(func.count()).select_from(CrmLead).where(
                *lead_filters, CrmLead.next_action.isnot(None), CrmLead.next_action != ""
            )
        ) or 0

        qualified_ids = [stage_key_to_id[k] for k in ("qualified", "scheduled", "won") if k in stage_key_to_id]
        scheduled_ids = [stage_key_to_id[k] for k in ("scheduled", "won") if k in stage_key_to_id]
        won_id = stage_key_to_id.get("won")

        def breakdown(column) -> tuple[FunnelBreakdown, ...]:
            rows = self.db.execute(
                select(
                    column,
                    func.count().label("total"),
                    func.sum(case((CrmLead.current_stage_id.in_(qualified_ids), 1), else_=0)).label("qualified"),
                    func.sum(case((CrmLead.current_stage_id.in_(scheduled_ids), 1), else_=0)).label("scheduled"),
                    func.sum(case((CrmLead.current_stage_id == won_id, 1), else_=0)).label("won"),
                )
                .where(*lead_filters, column.isnot(None), column != "")
                .group_by(column)
            ).all()
            return tuple(
                FunnelBreakdown(
                    name=r[0], total=r.total or 0, qualified=r.qualified or 0, scheduled=r.scheduled or 0, won=r.won or 0
                )
                for r in rows
            )

        return CrmFunnelSnapshot(
            stage_counts=stage_counts,
            total_leads=sum(counts_by_stage_id.values()),
            open_leads=open_leads,
            pending_tasks=pending_tasks,
            overdue_tasks=overdue_tasks,
            leads_with_next_action=leads_with_next_action,
            sources=breakdown(CrmLead.source),
            campaigns=breakdown(CrmLead.campaign),
        )

    def call_ids_for_leads(self, tenant_id: str, source: str | None, campaign: str | None) -> list[str]:
        """Call ids linked (last call, creating call, timeline) to the tenant's
        leads of a source/campaign."""
        lead_sub = select(CrmLead.id).where(CrmLead.tenant_id == tenant_id)
        if source:
            lead_sub = lead_sub.where(CrmLead.source == source)
        if campaign:
            lead_sub = lead_sub.where(CrmLead.campaign == campaign)
        lead_ids = self.db.scalars(lead_sub).all()
        call_ids: set[str] = set()
        if lead_ids:
            call_ids.update(
                self.db.scalars(
                    select(CrmLead.last_call_id).where(CrmLead.id.in_(lead_ids), CrmLead.last_call_id.isnot(None))
                ).all()
            )
            call_ids.update(
                self.db.scalars(
                    select(CrmLead.created_from_call_id).where(
                        CrmLead.id.in_(lead_ids), CrmLead.created_from_call_id.isnot(None)
                    )
                ).all()
            )
            call_ids.update(
                self.db.scalars(
                    select(CrmActivity.call_id).where(CrmActivity.lead_id.in_(lead_ids), CrmActivity.call_id.isnot(None))
                ).all()
            )
        return list(call_ids)

    def pending_action_candidates(
        self, tenant_id: str, source: str | None, campaign: str | None, *, offset: int, limit: int
    ) -> list[PendingActionCandidate]:
        """Leads that may need a human, newest first. ``requires_call_check`` marks
        the ones that qualify only if their last call was not answered (Analytics
        decides that; CRM does not read call state)."""
        stages = CrmPipelineService(self.db).ensure_default_pipeline(tenant_id)
        stage_key_to_id = {s.key: s.id for s in stages}
        follow_up_stage_id = stage_key_to_id.get("follow_up")
        contacted_stage_id = stage_key_to_id.get("contacted")
        task_lead_sub = select(CrmTask.lead_id).where(CrmTask.tenant_id == tenant_id, CrmTask.status == "pending")

        conditions = []
        if follow_up_stage_id:
            conditions.append(CrmLead.current_stage_id == follow_up_stage_id)
        if contacted_stage_id:
            conditions.append(CrmLead.current_stage_id == contacted_stage_id)
        conditions.append(and_(CrmLead.next_action.isnot(None), CrmLead.next_action != ""))
        conditions.append(CrmLead.id.in_(task_lead_sub))

        query = (
            select(CrmLead)
            .where(CrmLead.tenant_id == tenant_id, or_(*conditions))
            .options(joinedload(CrmLead.contact), joinedload(CrmLead.stage))
        )
        if source:
            query = query.where(CrmLead.source == source)
        if campaign:
            query = query.where(CrmLead.campaign == campaign)
        rows = self.db.scalars(
            query.order_by(CrmLead.updated_at.desc(), CrmLead.id).offset(offset).limit(limit)
        ).unique().all()

        task_lead_ids = set(self.db.scalars(task_lead_sub).all())
        out = []
        for lead in rows:
            has_next_action = bool(lead.next_action)
            qualifies_now = (
                lead.current_stage_id == follow_up_stage_id
                or has_next_action
                or lead.id in task_lead_ids
                or (contacted_stage_id is not None and lead.current_stage_id == contacted_stage_id and lead.last_call_id is None)
            )
            out.append(
                PendingActionCandidate(
                    lead_id=lead.id,
                    contact_name=self._display_contact_name(lead),
                    stage_key=lead.stage.key,
                    next_action=lead.next_action,
                    source=lead.source,
                    campaign=lead.campaign,
                    updated_at=lead.updated_at,
                    last_call_id=lead.last_call_id,
                    qualifies_without_call=qualifies_now,
                    requires_call_check=(
                        not qualifies_now
                        and contacted_stage_id is not None
                        and lead.current_stage_id == contacted_stage_id
                    ),
                )
            )
        return out

    def _display_contact_name(self, lead: CrmLead) -> str:
        filters = []
        if lead.context_id:
            filters.append(CrmCallContext.context_id == lead.context_id)
        if lead.form_submission_id:
            filters.append(CrmCallContext.form_submission_id == lead.form_submission_id)
        if filters:
            context = self.db.scalar(
                select(CrmCallContext)
                .where(CrmCallContext.tenant_id == lead.tenant_id, or_(*filters))
                .order_by(CrmCallContext.created_at.desc())
                .limit(1)
            )
            if context and context.name:
                return context.name
        return lead.contact.name or "Lead sin nombre"
