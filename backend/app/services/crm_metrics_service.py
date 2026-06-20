from __future__ import annotations

from datetime import UTC, datetime, timedelta
from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from app.models.crm import CrmContact, CrmLead, CrmActivity, CrmTask


class CrmMetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_metrics(
        self,
        tenant_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        source: str | None = None,
        campaign: str | None = None,
        assigned_agent_id: str | None = None,
    ) -> dict:
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        # Base lead filters
        lead_base = [CrmLead.tenant_id == tenant_id]
        if date_from:
            lead_base.append(CrmLead.created_at >= date_from)
        if date_to:
            lead_base.append(CrmLead.created_at <= date_to)
        if source:
            lead_base.append(CrmLead.source == source)
        if campaign:
            lead_base.append(CrmLead.campaign == campaign)
        if assigned_agent_id:
            lead_base.append(CrmLead.owner_agent_id == assigned_agent_id)

        # Contact base filter
        contact_base = [CrmContact.tenant_id == tenant_id]

        # Task base filter
        task_base = [CrmTask.tenant_id == tenant_id]

        # Total counts
        total_contacts = self.db.scalar(
            select(func.count()).select_from(CrmContact).where(*contact_base)
        ) or 0

        total_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead).where(*lead_base)
        ) or 0

        open_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.status == "open")
        ) or 0

        won_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.status == "won")
        ) or 0

        lost_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.status == "lost")
        ) or 0

        unqualified_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.status == "unqualified")
        ) or 0

        # Leads by stage
        stage_rows = self.db.execute(
            select(CrmLead.current_stage_id, func.count())
            .where(*lead_base)
            .group_by(CrmLead.current_stage_id)
        ).all()

        from app.services.crm_pipeline_service import CrmPipelineService
        pipeline_service = CrmPipelineService(self.db)
        stages = pipeline_service.ensure_default_pipeline(tenant_id)
        stage_map = {s.id: s for s in stages}

        leads_by_stage = []
        for stage_id, count in stage_rows:
            stage = stage_map.get(stage_id)
            if stage:
                leads_by_stage.append({
                    "stage_key": stage.key,
                    "stage_name": stage.name,
                    "count": count,
                })

        # Leads by source
        source_rows = self.db.execute(
            select(CrmLead.source, func.count())
            .where(*lead_base, CrmLead.source.isnot(None))
            .group_by(CrmLead.source)
        ).all()
        leads_by_source = [{"source": s, "count": c} for s, c in source_rows if s]

        # Leads by campaign
        campaign_rows = self.db.execute(
            select(CrmLead.campaign, func.count())
            .where(*lead_base, CrmLead.campaign.isnot(None))
            .group_by(CrmLead.campaign)
        ).all()
        leads_by_campaign = [{"campaign": c, "count": cnt} for c, cnt in campaign_rows if c]

        # Time-based lead counts
        leads_created_today = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.created_at >= today_start)
        ) or 0

        leads_created_this_week = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.created_at >= week_start)
        ) or 0

        leads_created_this_month = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_base, CrmLead.created_at >= month_start)
        ) or 0

        # Stage-based counts
        stage_key_map = {}
        for s in stages:
            stage_key_map[s.key] = s.id

        scheduled_leads = 0
        voicemail_leads = 0
        follow_up_leads = 0

        if "scheduled" in stage_key_map:
            scheduled_leads = self.db.scalar(
                select(func.count()).select_from(CrmLead)
                .where(*lead_base, CrmLead.current_stage_id == stage_key_map["scheduled"])
            ) or 0

        if "voicemail" in stage_key_map:
            voicemail_leads = self.db.scalar(
                select(func.count()).select_from(CrmLead)
                .where(*lead_base, CrmLead.current_stage_id == stage_key_map["voicemail"])
            ) or 0

        if "follow_up" in stage_key_map:
            follow_up_leads = self.db.scalar(
                select(func.count()).select_from(CrmLead)
                .where(*lead_base, CrmLead.current_stage_id == stage_key_map["follow_up"])
            ) or 0

        # Task counts
        pending_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask)
            .where(*task_base, CrmTask.status == "pending")
        ) or 0

        now_dt = datetime.now(UTC)
        overdue_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask)
            .where(
                *task_base,
                CrmTask.status == "pending",
                CrmTask.due_at.isnot(None),
                CrmTask.due_at < now_dt,
            )
        ) or 0

        # Conversion rate
        conversion_rate = 0.0
        if total_leads > 0:
            conversion_rate = round((won_leads / total_leads) * 100, 2)

        # Contact completion rate
        contacts_with_phone_or_email = self.db.scalar(
            select(func.count()).select_from(CrmContact)
            .where(
                *contact_base,
                case(
                    (CrmContact.phone.isnot(None), 1),
                    (CrmContact.email.isnot(None), 1),
                    else_=0
                ) == 1,
            )
        ) or 0

        contact_completion_rate = 0.0
        if total_contacts > 0:
            contact_completion_rate = round((contacts_with_phone_or_email / total_contacts) * 100, 2)

        return {
            "total_contacts": total_contacts,
            "total_leads": total_leads,
            "open_leads": open_leads,
            "won_leads": won_leads,
            "lost_leads": lost_leads,
            "unqualified_leads": unqualified_leads,
            "leads_by_stage": leads_by_stage,
            "leads_by_source": leads_by_source,
            "leads_by_campaign": leads_by_campaign,
            "leads_created_today": leads_created_today,
            "leads_created_this_week": leads_created_this_week,
            "leads_created_this_month": leads_created_this_month,
            "scheduled_leads": scheduled_leads,
            "voicemail_leads": voicemail_leads,
            "follow_up_leads": follow_up_leads,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "conversion_rate": conversion_rate,
            "contact_completion_rate": contact_completion_rate,
        }