from __future__ import annotations

from datetime import UTC, datetime, timedelta, time
from sqlalchemy import func, select, and_, or_, case
from sqlalchemy.orm import Session, joinedload
from zoneinfo import ZoneInfo

from app.models.crm import CrmContact, CrmLead, CrmActivity, CrmTask, CrmPipelineStage, CrmCallContext
from app.models.analytics import Call
from app.models.identity import Tenant
from app.services.crm_pipeline_service import CrmPipelineService


class CrmDashboardMetricsService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard(
        self,
        tenant: Tenant,
        range_val: str | None = None,
        date_from_str: str | None = None,
        date_to_str: str | None = None,
        source: str | None = None,
        campaign: str | None = None,
    ) -> dict:
        tenant_id = tenant.id
        timezone_str = tenant.timezone or "UTC"

        # Resolve timezone-aware date range
        date_from, date_to = self._resolve_date_range(range_val, date_from_str, date_to_str, timezone_str)

        # Convert to UTC for DB filtering
        date_from_utc = date_from.astimezone(UTC)
        date_to_utc = date_to.astimezone(UTC)

        # 1. Base pipeline stages setup
        pipeline_service = CrmPipelineService(self.db)
        stages = pipeline_service.ensure_default_pipeline(tenant_id)
        stage_key_to_id = {s.key: s.id for s in stages}
        stage_id_to_key = {s.id: s.key for s in stages}

        # 2. Base lead query filters
        lead_filters = [CrmLead.tenant_id == tenant_id]
        if date_from_utc:
            lead_filters.append(CrmLead.created_at >= date_from_utc)
        if date_to_utc:
            lead_filters.append(CrmLead.created_at <= date_to_utc)
        if source:
            lead_filters.append(CrmLead.source == source)
        if campaign:
            lead_filters.append(CrmLead.campaign == campaign)

        # 3. Get stage counts for active leads
        counts_query = (
            select(CrmLead.current_stage_id, func.count())
            .where(*lead_filters)
            .group_by(CrmLead.current_stage_id)
        )
        counts_res = self.db.execute(counts_query).all()
        counts_by_stage_id = {stage_id: cnt for stage_id, cnt in counts_res}

        # Stage specific counts
        new_leads = counts_by_stage_id.get(stage_key_to_id.get("new"), 0)
        contacted_leads = counts_by_stage_id.get(stage_key_to_id.get("contacted"), 0)
        connected_leads = counts_by_stage_id.get(stage_key_to_id.get("connected"), 0)
        qualified_leads = counts_by_stage_id.get(stage_key_to_id.get("qualified"), 0)
        scheduled_leads = counts_by_stage_id.get(stage_key_to_id.get("scheduled"), 0)
        voicemail_leads = counts_by_stage_id.get(stage_key_to_id.get("voicemail"), 0)
        follow_up_leads = counts_by_stage_id.get(stage_key_to_id.get("follow_up"), 0)
        not_interested_leads = counts_by_stage_id.get(stage_key_to_id.get("not_interested"), 0)
        won_leads = counts_by_stage_id.get(stage_key_to_id.get("won"), 0)
        lost_leads = counts_by_stage_id.get(stage_key_to_id.get("lost"), 0)

        # Calculate general KPIs
        total_leads = sum(counts_by_stage_id.values())

        open_leads = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_filters, CrmLead.status == "open")
        ) or 0

        pending_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask)
            .where(CrmTask.tenant_id == tenant_id, CrmTask.status == "pending")
        ) or 0

        now_utc = datetime.now(UTC)
        overdue_tasks = self.db.scalar(
            select(func.count()).select_from(CrmTask)
            .where(
                CrmTask.tenant_id == tenant_id,
                CrmTask.status == "pending",
                CrmTask.due_at.isnot(None),
                CrmTask.due_at < now_utc
            )
        ) or 0

        leads_with_next_action = self.db.scalar(
            select(func.count()).select_from(CrmLead)
            .where(*lead_filters, CrmLead.next_action.isnot(None), CrmLead.next_action != "")
        ) or 0

        kpis = {
            "total_leads": total_leads,
            "new_leads": new_leads,
            "contacted_leads": contacted_leads,
            "connected_leads": connected_leads,
            "qualified_leads": qualified_leads,
            "scheduled_leads": scheduled_leads,
            "voicemail_leads": voicemail_leads,
            "follow_up_leads": follow_up_leads,
            "not_interested_leads": not_interested_leads,
            "won_leads": won_leads,
            "lost_leads": lost_leads,
            "open_leads": open_leads,
            "pending_tasks": pending_tasks,
            "overdue_tasks": overdue_tasks,
            "leads_with_next_action": leads_with_next_action,
        }

        # 4. Conversion Rates (Cumulative Logic)
        def get_count_of_keys(keys_list: list[str]) -> int:
            return sum(counts_by_stage_id.get(stage_key_to_id.get(k), 0) for k in keys_list if k in stage_key_to_id)

        contacted_cum = get_count_of_keys(["contacted", "connected", "qualified", "scheduled", "won", "voicemail", "follow_up", "not_interested", "lost"])
        connected_cum = get_count_of_keys(["connected", "qualified", "scheduled", "won", "follow_up", "not_interested", "lost"])
        qualified_cum = get_count_of_keys(["qualified", "scheduled", "won"])
        scheduled_cum = get_count_of_keys(["scheduled", "won"])
        won_cum = get_count_of_keys(["won"])

        contact_rate = round((contacted_cum / total_leads * 100), 2) if total_leads > 0 else 0.0
        connection_rate = round((connected_cum / contacted_cum * 100), 2) if contacted_cum > 0 else 0.0
        qualification_rate = round((qualified_cum / connected_cum * 100), 2) if connected_cum > 0 else 0.0
        schedule_rate = round((scheduled_cum / qualified_cum * 100), 2) if qualified_cum > 0 else 0.0
        win_rate = round((won_cum / scheduled_cum * 100), 2) if scheduled_cum > 0 else 0.0

        conversion = {
            "contact_rate": contact_rate,
            "connection_rate": connection_rate,
            "qualification_rate": qualification_rate,
            "schedule_rate": schedule_rate,
            "win_rate": win_rate,
        }

        # 5. Funnel Stage Counts
        funnel = [
            {"stage": "new", "label": "Nuevo", "count": new_leads},
            {"stage": "contacted", "label": "Contactado", "count": contacted_leads},
            {"stage": "connected", "label": "Conectado", "count": connected_leads},
            {"stage": "qualified", "label": "Calificado", "count": qualified_leads},
            {"stage": "scheduled", "label": "Agendado", "count": scheduled_leads},
            {"stage": "won", "label": "Ganado", "count": won_leads},
        ]

        # 6. Source Breakdown
        source_query = (
            select(
                CrmLead.source,
                func.count().label("total"),
                func.sum(case((CrmLead.current_stage_id.in_([stage_key_to_id.get(k) for k in ["qualified", "scheduled", "won"] if k in stage_key_to_id]), 1), else_=0)).label("qualified"),
                func.sum(case((CrmLead.current_stage_id.in_([stage_key_to_id.get(k) for k in ["scheduled", "won"] if k in stage_key_to_id]), 1), else_=0)).label("scheduled"),
                func.sum(case((CrmLead.current_stage_id == stage_key_to_id.get("won"), 1), else_=0)).label("won")
            )
            .where(*lead_filters, CrmLead.source.isnot(None), CrmLead.source != "")
            .group_by(CrmLead.source)
        )
        source_rows = self.db.execute(source_query).all()
        sources_list = []
        for r in source_rows:
            tot = r.total or 0
            wn = r.won or 0
            conv_rate = round((wn / tot * 100), 2) if tot > 0 else 0.0
            sources_list.append({
                "source": r.source,
                "total_leads": tot,
                "qualified_leads": r.qualified or 0,
                "scheduled_leads": r.scheduled or 0,
                "won_leads": wn,
                "conversion_rate": conv_rate
            })

        # 7. Campaign Breakdown
        campaign_query = (
            select(
                CrmLead.campaign,
                func.count().label("total"),
                func.sum(case((CrmLead.current_stage_id.in_([stage_key_to_id.get(k) for k in ["qualified", "scheduled", "won"] if k in stage_key_to_id]), 1), else_=0)).label("qualified"),
                func.sum(case((CrmLead.current_stage_id.in_([stage_key_to_id.get(k) for k in ["scheduled", "won"] if k in stage_key_to_id]), 1), else_=0)).label("scheduled"),
                func.sum(case((CrmLead.current_stage_id == stage_key_to_id.get("won"), 1), else_=0)).label("won")
            )
            .where(*lead_filters, CrmLead.campaign.isnot(None), CrmLead.campaign != "")
            .group_by(CrmLead.campaign)
        )
        campaign_rows = self.db.execute(campaign_query).all()
        campaigns_list = []
        for r in campaign_rows:
            tot = r.total or 0
            wn = r.won or 0
            conv_rate = round((wn / tot * 100), 2) if tot > 0 else 0.0
            campaigns_list.append({
                "campaign": r.campaign,
                "total_leads": tot,
                "qualified_leads": r.qualified or 0,
                "scheduled_leads": r.scheduled or 0,
                "won_leads": wn,
                "conversion_rate": conv_rate
            })

        # 8. Calls Metrics
        call_filters = [Call.tenant_id == tenant_id]
        if date_from_utc:
            call_filters.append(Call.started_at >= date_from_utc)
        if date_to_utc:
            call_filters.append(Call.started_at <= date_to_utc)

        if source or campaign:
            lead_sub = select(CrmLead.id).where(CrmLead.tenant_id == tenant_id)
            if source:
                lead_sub = lead_sub.where(CrmLead.source == source)
            if campaign:
                lead_sub = lead_sub.where(CrmLead.campaign == campaign)
            lead_ids = self.db.scalars(lead_sub).all()
            call_ids = set()
            if lead_ids:
                lc_ids = self.db.scalars(select(CrmLead.last_call_id).where(CrmLead.id.in_(lead_ids), CrmLead.last_call_id.isnot(None))).all()
                call_ids.update(lc_ids)
                cfc_ids = self.db.scalars(select(CrmLead.created_from_call_id).where(CrmLead.id.in_(lead_ids), CrmLead.created_from_call_id.isnot(None))).all()
                call_ids.update(cfc_ids)
                act_cids = self.db.scalars(select(CrmActivity.call_id).where(CrmActivity.lead_id.in_(lead_ids), CrmActivity.call_id.isnot(None))).all()
                call_ids.update(act_cids)
            call_filters.append(Call.id.in_(list(call_ids) if call_ids else ["non-existent-id"]))

        calls_list = self.db.scalars(select(Call).where(*call_filters)).all()

        total_calls = len(calls_list)
        answered_calls = sum(1 for c in calls_list if c.normalized_status == "answered")
        unanswered_calls = sum(1 for c in calls_list if c.normalized_status == "unanswered")
        voicemail_calls = sum(1 for c in calls_list if c.normalized_status == "voicemail")
        failed_calls = sum(1 for c in calls_list if c.normalized_status == "failed")

        durations = [c.duration_seconds for c in calls_list if c.duration_seconds is not None]
        avg_dur = round((sum(durations) / len(durations)), 2) if durations else 0.0
        tot_billed = round(float(sum(c.billed_minutes or 0 for c in calls_list)), 2)

        calls = {
            "total_calls": total_calls,
            "answered_calls": answered_calls,
            "unanswered_calls": unanswered_calls,
            "voicemail_calls": voicemail_calls,
            "failed_calls": failed_calls,
            "average_duration_seconds": avg_dur,
            "total_billed_minutes": tot_billed,
        }

        # 9. Pending Actions (Human intervention required)
        follow_up_stage_id = stage_key_to_id.get("follow_up")
        contacted_stage_id = stage_key_to_id.get("contacted")

        task_lead_sub = select(CrmTask.lead_id).where(CrmTask.tenant_id == tenant_id, CrmTask.status == "pending")

        pending_actions_conditions = []
        if follow_up_stage_id:
            pending_actions_conditions.append(CrmLead.current_stage_id == follow_up_stage_id)
        if contacted_stage_id:
            pending_actions_conditions.append(
                and_(
                    CrmLead.current_stage_id == contacted_stage_id,
                    or_(
                        CrmLead.last_call_id.is_(None),
                        Call.normalized_status != "answered"
                    )
                )
            )
        pending_actions_conditions.append(
            and_(
                CrmLead.next_action.isnot(None),
                CrmLead.next_action != ""
            )
        )
        pending_actions_conditions.append(
            CrmLead.id.in_(task_lead_sub)
        )

        pending_actions_query = (
            select(CrmLead)
            .outerjoin(Call, Call.id == CrmLead.last_call_id)
            .where(
                CrmLead.tenant_id == tenant_id,
                or_(*pending_actions_conditions)
            )
            .options(
                joinedload(CrmLead.contact),
                joinedload(CrmLead.stage)
            )
        )

        if source:
            pending_actions_query = pending_actions_query.where(CrmLead.source == source)
        if campaign:
            pending_actions_query = pending_actions_query.where(CrmLead.campaign == campaign)

        pending_actions_query = pending_actions_query.order_by(CrmLead.updated_at.desc()).limit(20)
        pending_leads = self.db.scalars(pending_actions_query).unique().all()

        pending_actions_list = []
        for pl in pending_leads:
            pending_actions_list.append({
                "lead_id": pl.id,
                "contact_name": self._display_contact_name(pl),
                "stage": pl.stage.key,
                "next_action": pl.next_action,
                "source": pl.source,
                "campaign": pl.campaign,
                "updated_at": pl.updated_at,
            })

        # Period payload
        period = {
            "from": date_from.date().isoformat(),
            "to": date_to.date().isoformat(),
            "range": range_val or "30d",
        }

        return {
            "period": period,
            "kpis": kpis,
            "conversion": conversion,
            "funnel": funnel,
            "sources": sources_list,
            "campaigns": campaigns_list,
            "calls": calls,
            "pending_actions": pending_actions_list,
        }

    def _resolve_date_range(
        self,
        range_val: str | None,
        date_from_str: str | None,
        date_to_str: str | None,
        timezone_str: str,
    ) -> tuple[datetime, datetime]:
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("UTC")

        now = datetime.now(tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        if range_val == "today":
            df = today_start
            dt = today_end
        elif range_val == "7d":
            df = today_start - timedelta(days=6)
            dt = today_end
        elif range_val == "month":
            df = today_start.replace(day=1)
            dt = today_end
        elif range_val == "custom":
            if not date_from_str or not date_to_str:
                df = today_start - timedelta(days=29)
                dt = today_end
            else:
                try:
                    if len(date_from_str) == 10:
                        d_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
                        df = datetime.combine(d_from, time.min, tzinfo=tz)
                    else:
                        df = datetime.fromisoformat(date_from_str.replace("Z", "+00:00")).astimezone(tz)

                    if len(date_to_str) == 10:
                        d_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
                        dt = datetime.combine(d_to, time.max, tzinfo=tz)
                    else:
                        dt = datetime.fromisoformat(date_to_str.replace("Z", "+00:00")).astimezone(tz)
                except Exception:
                    df = today_start - timedelta(days=29)
                    dt = today_end
        else:
            df = today_start - timedelta(days=29)
            dt = today_end

        return df, dt

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
