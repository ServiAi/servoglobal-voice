from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.crm import CrmBooking
from app.models.integrations import (
    TenantAgentSchedulingConfig,
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingAvailabilityException,
    TenantSchedulingConfig,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
    TenantSchedulingTeam,
    TenantSchedulingTeamMember,
)
from app.services.calcom_service import (
    _build_summary,
    _in_jornada,
    _resolve_date_input,
)
from app.services.date_resolution_service import parse_reference_datetime
from app.services.google_calendar_service import GoogleCalendarService
from app.services.scheduling_config_service import SchedulingConfigService

logger = logging.getLogger(__name__)

DIAS_SEMANA_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _normalize_shifts(day_data: Any) -> list[tuple[str, str]]:
    """
    Normalizes working hours data for a single day into a list of (start_hh_mm, end_hh_mm).
    Handles:
      - [{"start": "08:00", "end": "12:00"}, {"start": "14:00", "end": "18:00"}]
      - [("08:00", "12:00"), ("14:00", "18:00")]
      - ("08:00", "18:00") or ["08:00", "18:00"]
      - {"start": "08:00", "end": "18:00"}
    """
    if not day_data:
        return []
    if isinstance(day_data, dict):
        if "start" in day_data and "end" in day_data:
            return [(str(day_data["start"]), str(day_data["end"]))]
        return []
    if isinstance(day_data, (tuple, list)):
        if len(day_data) == 2 and isinstance(day_data[0], str) and isinstance(day_data[1], str):
            return [(str(day_data[0]), str(day_data[1]))]
        shifts: list[tuple[str, str]] = []
        for item in day_data:
            if isinstance(item, dict) and "start" in item and "end" in item:
                shifts.append((str(item["start"]), str(item["end"])))
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                shifts.append((str(item[0]), str(item[1])))
        return shifts
    return []


def _resolve_day_shifts(
    weekday_idx: int,
    working_hours: dict[str, Any] | None,
) -> list[tuple[str, str]]:
    """Resolves shifts for a day of week from working_hours dict or defaults."""
    day_name = WEEKDAY_NAMES[weekday_idx]
    if working_hours:
        if day_name in working_hours:
            return _normalize_shifts(working_hours[day_name])
        if weekday_idx < 5 and "weekday" in working_hours:
            return _normalize_shifts(working_hours["weekday"])
        if weekday_idx == 5 and "saturday" in working_hours:
            return _normalize_shifts(working_hours["saturday"])
        if weekday_idx == 6 and "sunday" in working_hours:
            return _normalize_shifts(working_hours["sunday"])
        return []

    # Default working hours
    if weekday_idx < 5:
        return [("08:00", "18:00")]
    if weekday_idx == 5:
        return [("08:00", "13:00")]
    return []


class SchedulingAvailabilityService:
    def __init__(
        self,
        db: Session,
        google_calendar_service: GoogleCalendarService | None = None,
    ) -> None:
        self.db = db
        self.google_calendar_service = google_calendar_service or GoogleCalendarService(db)

    def get_available_slots(
        self,
        *,
        tenant_id: str,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
        timezone_str: str | None = None,
        slot_duration_minutes: int | None = None,
        slot_interval_minutes: int | None = None,
        buffer_minutes: int | None = None,
        buffer_before_minutes: int | None = None,
        buffer_after_minutes: int | None = None,
        min_notice_minutes: int | None = None,
        working_hours: dict[str, Any] | None = None,
        resource_id: str | None = None,
        team_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        # 1. Load tenant scheduling config
        config = SchedulingConfigService(self.db).get_or_create_config(tenant_id)

        # 2. Check if agent_id has overrides
        if agent_id:
            agent_cfg = self.db.scalar(
                select(TenantAgentSchedulingConfig).where(
                    TenantAgentSchedulingConfig.tenant_id == tenant_id,
                    TenantAgentSchedulingConfig.agent_id == agent_id,
                    TenantAgentSchedulingConfig.is_active == True,  # noqa: E712
                )
            )
            if agent_cfg:
                if agent_cfg.team_id and not team_id:
                    team_id = agent_cfg.team_id
                if agent_cfg.resource_id and not resource_id:
                    resource_id = agent_cfg.resource_id
                if agent_cfg.duration_minutes and not slot_duration_minutes:
                    slot_duration_minutes = agent_cfg.duration_minutes

        effective_tz = timezone_str or config.timezone or "America/Bogota"
        duration = slot_duration_minutes or config.default_duration_minutes or 30
        interval = slot_interval_minutes or config.slot_interval_minutes or duration
        notice_mins = min_notice_minutes if min_notice_minutes is not None else config.minimum_notice_minutes
        max_days = config.maximum_booking_days or 60

        buf_before = buffer_before_minutes if buffer_before_minutes is not None else (
            buffer_minutes if buffer_minutes is not None else config.buffer_before_minutes
        )
        buf_after = buffer_after_minutes if buffer_after_minutes is not None else (
            buffer_minutes if buffer_minutes is not None else config.buffer_after_minutes
        )

        try:
            tz = ZoneInfo(effective_tz)
        except Exception:
            tz = ZoneInfo("America/Bogota")

        start_date_str, _, temporal_resolution = _resolve_date_input(date_input, reference_datetime)
        target_date = date.fromisoformat(start_date_str)

        ref_now = parse_reference_datetime(reference_datetime)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=tz)
        else:
            ref_now = ref_now.astimezone(tz)

        # Check date bounds
        delta_days = (target_date - ref_now.date()).days
        if delta_days < 0:
            return self._empty_response(
                target_date_str=start_date_str,
                jornada=jornada,
                ref_now=ref_now,
                temporal_resolution=temporal_resolution,
                reason="Fecha pasada",
            )
        if delta_days > max_days:
            return self._empty_response(
                target_date_str=start_date_str,
                jornada=jornada,
                ref_now=ref_now,
                temporal_resolution=temporal_resolution,
                reason=f"Excede ventana máxima de reserva ({max_days} días)",
            )

        # Resolve effective routing target
        effective_resource_id = resource_id
        effective_team_id = team_id
        if not effective_resource_id and not effective_team_id:
            if config.routing_strategy == "team" and config.default_team_id:
                effective_team_id = config.default_team_id
            elif config.routing_strategy == "resource" and config.default_resource_id:
                effective_resource_id = config.default_resource_id

        # 3. Check exceptions for the day
        exc_stmt = select(TenantSchedulingAvailabilityException).where(
            TenantSchedulingAvailabilityException.tenant_id == tenant_id,
            TenantSchedulingAvailabilityException.exception_date == target_date,
        )
        if effective_resource_id:
            exc_stmt = exc_stmt.where(
                (TenantSchedulingAvailabilityException.resource_id == effective_resource_id)
                | (TenantSchedulingAvailabilityException.resource_id.is_(None))
            )
        else:
            exc_stmt = exc_stmt.where(TenantSchedulingAvailabilityException.resource_id.is_(None))

        exceptions = list(self.db.scalars(exc_stmt).all())
        # Check for unavailable exception
        for exc in exceptions:
            if exc.exception_type == "unavailable":
                return self._empty_response(
                    target_date_str=start_date_str,
                    jornada=jornada,
                    ref_now=ref_now,
                    temporal_resolution=temporal_resolution,
                    reason=exc.reason or "Día no laborable (excepción)",
                )

        # 4. Resolve shifts for the day
        custom_shifts: list[tuple[str, str]] | None = None
        for exc in exceptions:
            if exc.exception_type == "custom_hours" and exc.start_time and exc.end_time:
                custom_shifts = [(exc.start_time, exc.end_time)]
                break

        if custom_shifts is not None:
            shifts = custom_shifts
        else:
            hours_source = working_hours
            if hours_source is None and effective_resource_id:
                res = self.db.scalar(
                    select(TenantSchedulingResource).where(
                        TenantSchedulingResource.id == effective_resource_id,
                        TenantSchedulingResource.tenant_id == tenant_id,
                    )
                )
                if res and res.working_hours_json:
                    hours_source = res.working_hours_json
            if hours_source is None:
                hours_source = config.working_hours_json

            shifts = _resolve_day_shifts(target_date.weekday(), hours_source)

        if not shifts:
            return self._empty_response(
                target_date_str=start_date_str,
                jornada=jornada,
                ref_now=ref_now,
                temporal_resolution=temporal_resolution,
                reason="Día no laborable",
            )

        # 5. Delegate team routing or resource/tenant routing
        if effective_team_id:
            slots_raw = self._get_team_slots(
                tenant_id=tenant_id,
                team_id=effective_team_id,
                target_date=target_date,
                shifts=shifts,
                tz=tz,
                ref_now=ref_now,
                duration=duration,
                interval=interval,
                buf_before=buf_before,
                buf_after=buf_after,
                notice_mins=notice_mins,
                jornada=jornada,
            )
        else:
            slots_raw = self._get_slots_for_busy_intervals(
                tenant_id=tenant_id,
                resource_id=effective_resource_id,
                target_date=target_date,
                shifts=shifts,
                tz=tz,
                ref_now=ref_now,
                duration=duration,
                interval=interval,
                buf_before=buf_before,
                buf_after=buf_after,
                notice_mins=notice_mins,
                jornada=jornada,
            )

        summary_slots = [{"start": slot.get("time", slot["start"])} for slot in slots_raw]
        return {
            "metadata_consulta": {
                "fecha_ejecucion": ref_now.strftime("%Y-%m-%d %H:%M:%S"),
                "dia_semana": DIAS_SEMANA_ES[target_date.weekday()],
                "jornada_solicitada": jornada or "todas",
                "temporal_resolution": temporal_resolution,
                "provider": "google_calendar",
            },
            "date": start_date_str,
            "jornada": jornada or "all",
            "available_slots": slots_raw,
            "summary": _build_summary(summary_slots, start_date_str, jornada),
        }

    def _get_slots_for_busy_intervals(
        self,
        *,
        tenant_id: str,
        resource_id: str | None,
        target_date: date,
        shifts: list[tuple[str, str]],
        tz: ZoneInfo,
        ref_now: datetime,
        duration: int,
        interval: int,
        buf_before: int,
        buf_after: int,
        notice_mins: int,
        jornada: str | None,
    ) -> list[dict[str, str]]:
        day_earliest_local = min(time(int(s[0].split(":")[0]), int(s[0].split(":")[1])) for s in shifts)
        day_latest_local = max(time(int(s[1].split(":")[0]), int(s[1].split(":")[1])) for s in shifts)

        day_start_utc = datetime.combine(target_date, day_earliest_local, tzinfo=tz).astimezone(UTC)
        day_end_utc = datetime.combine(target_date, day_latest_local, tzinfo=tz).astimezone(UTC)

        # Collect busy intervals
        busy_intervals = self._collect_busy_intervals(
            tenant_id=tenant_id,
            resource_id=resource_id,
            time_min_utc=day_start_utc,
            time_max_utc=day_end_utc,
        )

        step_delta = timedelta(minutes=interval)
        slot_delta = timedelta(minutes=duration)
        buf_before_delta = timedelta(minutes=buf_before)
        buf_after_delta = timedelta(minutes=buf_after)
        earliest_allowed_utc = ref_now.astimezone(UTC) + timedelta(minutes=notice_mins)

        slots_raw: list[dict[str, str]] = []
        for start_str, end_str in shifts:
            s_h, s_m = [int(p) for p in start_str.split(":")]
            e_h, e_m = [int(p) for p in end_str.split(":")]
            shift_start_local = datetime.combine(target_date, time(s_h, s_m), tzinfo=tz)
            shift_end_local = datetime.combine(target_date, time(e_h, e_m), tzinfo=tz)

            current_local = shift_start_local
            while current_local + slot_delta <= shift_end_local:
                slot_start_utc = current_local.astimezone(UTC)
                slot_end_utc = (current_local + slot_delta).astimezone(UTC)

                if slot_start_utc >= earliest_allowed_utc:
                    collides = False
                    for busy_start, busy_end in busy_intervals:
                        if (slot_start_utc - buf_before_delta) < busy_end and (slot_end_utc + buf_after_delta) > busy_start:
                            collides = True
                            break

                    if not collides:
                        time_part = current_local.strftime("%H:%M")
                        if _in_jornada(time_part, jornada):
                            slots_raw.append({
                                "start": current_local.isoformat(),
                                "time": time_part,
                            })

                current_local += step_delta

        return slots_raw

    def _get_team_slots(
        self,
        *,
        tenant_id: str,
        team_id: str,
        target_date: date,
        shifts: list[tuple[str, str]],
        tz: ZoneInfo,
        ref_now: datetime,
        duration: int,
        interval: int,
        buf_before: int,
        buf_after: int,
        notice_mins: int,
        jornada: str | None,
    ) -> list[dict[str, str]]:
        team = self.db.scalar(
            select(TenantSchedulingTeam)
            .options(joinedload(TenantSchedulingTeam.members).joinedload(TenantSchedulingTeamMember.resource))
            .where(
                TenantSchedulingTeam.tenant_id == tenant_id,
                TenantSchedulingTeam.id == team_id,
                TenantSchedulingTeam.is_active == True,  # noqa: E712
            )
        )
        if not team or not team.members:
            return []

        active_members = [m.resource for m in team.members if m.is_active and m.resource and m.resource.is_active]
        if not active_members:
            return []

        # Candidate slots across team shifts
        day_earliest_local = min(time(int(s[0].split(":")[0]), int(s[0].split(":")[1])) for s in shifts)
        day_latest_local = max(time(int(s[1].split(":")[0]), int(s[1].split(":")[1])) for s in shifts)
        day_start_utc = datetime.combine(target_date, day_earliest_local, tzinfo=tz).astimezone(UTC)
        day_end_utc = datetime.combine(target_date, day_latest_local, tzinfo=tz).astimezone(UTC)

        # Precompute busy intervals and exceptions per member
        member_busy: dict[str, list[tuple[datetime, datetime]]] = {}
        member_unavailable: set[str] = set()

        for res in active_members:
            # Check resource exception for the day
            exc = self.db.scalar(
                select(TenantSchedulingAvailabilityException).where(
                    TenantSchedulingAvailabilityException.tenant_id == tenant_id,
                    TenantSchedulingAvailabilityException.resource_id == res.id,
                    TenantSchedulingAvailabilityException.exception_date == target_date,
                )
            )
            if exc and exc.exception_type == "unavailable":
                member_unavailable.add(res.id)
                continue

            member_busy[res.id] = self._collect_busy_intervals(
                tenant_id=tenant_id,
                resource_id=res.id,
                time_min_utc=day_start_utc,
                time_max_utc=day_end_utc,
            )

        step_delta = timedelta(minutes=interval)
        slot_delta = timedelta(minutes=duration)
        buf_before_delta = timedelta(minutes=buf_before)
        buf_after_delta = timedelta(minutes=buf_after)
        earliest_allowed_utc = ref_now.astimezone(UTC) + timedelta(minutes=notice_mins)

        slots_raw: list[dict[str, str]] = []
        for start_str, end_str in shifts:
            s_h, s_m = [int(p) for p in start_str.split(":")]
            e_h, e_m = [int(p) for p in end_str.split(":")]
            shift_start_local = datetime.combine(target_date, time(s_h, s_m), tzinfo=tz)
            shift_end_local = datetime.combine(target_date, time(e_h, e_m), tzinfo=tz)

            current_local = shift_start_local
            while current_local + slot_delta <= shift_end_local:
                slot_start_utc = current_local.astimezone(UTC)
                slot_end_utc = (current_local + slot_delta).astimezone(UTC)

                if slot_start_utc >= earliest_allowed_utc:
                    # Slot is available if AT LEAST ONE member is free
                    any_member_free = False
                    for res in active_members:
                        if res.id in member_unavailable:
                            continue

                        # Check resource custom working hours if defined
                        if res.working_hours_json:
                            day_name = WEEKDAY_NAMES[target_date.weekday()]
                            res_shifts = _normalize_shifts(res.working_hours_json.get(day_name, []))
                            if not res_shifts:
                                continue
                            slot_time_str = current_local.strftime("%H:%M")
                            slot_end_str = (current_local + slot_delta).strftime("%H:%M")
                            if not any(r[0] <= slot_time_str and slot_end_str <= r[1] for r in res_shifts):
                                continue

                        # Check collisions with member busy intervals
                        collides = False
                        for busy_start, busy_end in member_busy.get(res.id, []):
                            if (slot_start_utc - buf_before_delta) < busy_end and (slot_end_utc + buf_after_delta) > busy_start:
                                collides = True
                                break

                        if not collides:
                            any_member_free = True
                            break

                    if any_member_free:
                        time_part = current_local.strftime("%H:%M")
                        if _in_jornada(time_part, jornada):
                            slots_raw.append({
                                "start": current_local.isoformat(),
                                "time": time_part,
                            })

                current_local += step_delta

        return slots_raw

    def _collect_busy_intervals(
        self,
        *,
        tenant_id: str,
        resource_id: str | None,
        time_min_utc: datetime,
        time_max_utc: datetime,
    ) -> list[tuple[datetime, datetime]]:
        busy_intervals: list[tuple[datetime, datetime]] = []

        # 1. Google Calendar FreeBusy
        if resource_id:
            # Query calendars mapped to resource
            res_cals = list(
                self.db.scalars(
                    select(TenantSchedulingResourceCalendar)
                    .options(joinedload(TenantSchedulingResourceCalendar.calendar))
                    .where(
                        TenantSchedulingResourceCalendar.tenant_id == tenant_id,
                        TenantSchedulingResourceCalendar.resource_id == resource_id,
                        TenantSchedulingResourceCalendar.is_blocking == True,  # noqa: E712
                    )
                ).all()
            )
            blocking_cals = [rc.calendar for rc in res_cals if rc.calendar]
        else:
            blocking_cals = list(
                self.db.scalars(
                    select(TenantGoogleCalendar)
                    .join(TenantGoogleCalendarConnection, TenantGoogleCalendar.connection_id == TenantGoogleCalendarConnection.id)
                    .where(
                        TenantGoogleCalendar.tenant_id == tenant_id,
                        TenantGoogleCalendar.is_blocking == True,  # noqa: E712
                        TenantGoogleCalendarConnection.status == "connected",
                    )
                ).all()
            )

        cals_by_connection: dict[str, list[TenantGoogleCalendar]] = {}
        for cal in blocking_cals:
            cals_by_connection.setdefault(cal.connection_id, []).append(cal)

        for conn_id, cals in cals_by_connection.items():
            conn = self.db.get(TenantGoogleCalendarConnection, conn_id)
            if not conn or conn.status != "connected":
                continue
            cal_ids = [c.google_calendar_id for c in cals]
            try:
                g_busy = self.google_calendar_service.get_freebusy_intervals(
                    connection=conn,
                    calendar_ids=cal_ids,
                    time_min=time_min_utc,
                    time_max=time_max_utc,
                )
                for item in g_busy:
                    busy_intervals.append((item["start"], item["end"]))
            except Exception as exc:
                logger.warning("Error fetching FreeBusy for connection %s: %s", conn_id, exc)

        # 2. Existing CrmBookings
        b_stmt = select(CrmBooking).where(
            CrmBooking.tenant_id == tenant_id,
            CrmBooking.status.in_(["pending", "confirmed", "scheduled", "accepted"]),
            CrmBooking.start_at < time_max_utc,
            CrmBooking.end_at > time_min_utc,
        )
        if resource_id:
            res = self.db.scalar(
                select(TenantSchedulingResource).where(
                    TenantSchedulingResource.id == resource_id,
                    TenantSchedulingResource.tenant_id == tenant_id,
                )
            )
            if res and res.email:
                b_stmt = b_stmt.where(
                    (CrmBooking.host_email == res.email)
                    | (CrmBooking.metadata_json["scheduling_resource_id"].as_string() == resource_id)
                )
            else:
                b_stmt = b_stmt.where(CrmBooking.metadata_json["scheduling_resource_id"].as_string() == resource_id)

        crm_bookings = list(self.db.scalars(b_stmt).all())
        for b in crm_bookings:
            end_at = b.end_at or (b.start_at + timedelta(minutes=b.duration_minutes or 30))
            busy_intervals.append((b.start_at, end_at))

        return busy_intervals

    def _empty_response(
        self,
        *,
        target_date_str: str,
        jornada: str | None,
        ref_now: datetime,
        temporal_resolution: Any,
        reason: str,
    ) -> dict[str, Any]:
        target_date = date.fromisoformat(target_date_str)
        return {
            "metadata_consulta": {
                "fecha_ejecucion": ref_now.strftime("%Y-%m-%d %H:%M:%S"),
                "dia_semana": DIAS_SEMANA_ES[target_date.weekday()],
                "jornada_solicitada": jornada or "todas",
                "temporal_resolution": temporal_resolution,
                "provider": "google_calendar",
                "reason": reason,
            },
            "date": target_date_str,
            "jornada": jornada or "all",
            "available_slots": [],
            "summary": f"No hay disponibilidad para el {target_date_str} ({reason}).",
        }
