from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tenant
from app.models.analytics import Call
from app.modules.crm.public import CrmFacade
from app.services.voice_capacity_report_service import VoiceCapacityReportService


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

        crm = CrmFacade(self.db)
        funnel_snapshot = crm.dashboard_funnel(tenant_id, date_from_utc, date_to_utc, source, campaign)
        stage_counts = funnel_snapshot.stage_counts

        # Stage specific counts
        new_leads = stage_counts.get("new", 0)
        contacted_leads = stage_counts.get("contacted", 0)
        connected_leads = stage_counts.get("connected", 0)
        qualified_leads = stage_counts.get("qualified", 0)
        scheduled_leads = stage_counts.get("scheduled", 0)
        voicemail_leads = stage_counts.get("voicemail", 0)
        follow_up_leads = stage_counts.get("follow_up", 0)
        not_interested_leads = stage_counts.get("not_interested", 0)
        won_leads = stage_counts.get("won", 0)
        lost_leads = stage_counts.get("lost", 0)

        # Calculate general KPIs
        total_leads = funnel_snapshot.total_leads
        open_leads = funnel_snapshot.open_leads
        pending_tasks = funnel_snapshot.pending_tasks
        overdue_tasks = funnel_snapshot.overdue_tasks
        leads_with_next_action = funnel_snapshot.leads_with_next_action

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
            return sum(stage_counts.get(k, 0) for k in keys_list if k in stage_counts)

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
        sources_list = []
        for r in funnel_snapshot.sources:
            tot = r.total or 0
            wn = r.won or 0
            conv_rate = round((wn / tot * 100), 2) if tot > 0 else 0.0
            sources_list.append({
                "source": r.name,
                "total_leads": tot,
                "qualified_leads": r.qualified or 0,
                "scheduled_leads": r.scheduled or 0,
                "won_leads": wn,
                "conversion_rate": conv_rate
            })

        # 7. Campaign Breakdown
        campaigns_list = []
        for r in funnel_snapshot.campaigns:
            tot = r.total or 0
            wn = r.won or 0
            conv_rate = round((wn / tot * 100), 2) if tot > 0 else 0.0
            campaigns_list.append({
                "campaign": r.name,
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
            call_ids = crm.dashboard_call_ids(tenant_id, source, campaign)
            call_filters.append(Call.id.in_(call_ids if call_ids else ["non-existent-id"]))

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
        # CRM lists the candidates (newest first); whether a "contacted" lead's last
        # call was answered is Analytics' fact, checked here.
        pending_actions_list = []
        offset, page = 0, 100
        while len(pending_actions_list) < 20:
            candidates = crm.dashboard_pending_action_candidates(tenant_id, source, campaign, offset=offset, limit=page)
            if not candidates:
                break
            statuses: dict[str, str | None] = {}
            check_ids = [c.last_call_id for c in candidates if c.requires_call_check and c.last_call_id]
            if check_ids:
                statuses = dict(
                    self.db.execute(
                        select(Call.id, Call.normalized_status).where(Call.id.in_(check_ids))
                    ).all()
                )
            for candidate in candidates:
                qualifies = candidate.qualifies_without_call or (
                    candidate.requires_call_check
                    and candidate.last_call_id is not None
                    and statuses.get(candidate.last_call_id) is not None
                    and statuses[candidate.last_call_id] != "answered"
                )
                if not qualifies:
                    continue
                pending_actions_list.append({
                    "lead_id": candidate.lead_id,
                    "contact_name": candidate.contact_name,
                    "stage": candidate.stage_key,
                    "next_action": candidate.next_action,
                    "source": candidate.source,
                    "campaign": candidate.campaign,
                    "updated_at": candidate.updated_at,
                })
                if len(pending_actions_list) >= 20:
                    break
            if len(candidates) < page:
                break
            offset += page

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
            "voice_capacity": VoiceCapacityReportService(self.db).dashboard_snapshot(
                tenant_id=tenant_id,
                date_from=date_from_utc,
                date_to=date_to_utc,
            ),
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
