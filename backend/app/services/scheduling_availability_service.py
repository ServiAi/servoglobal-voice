from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.crm import CrmBooking
from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.services.calcom_service import (
    _build_summary,
    _in_jornada,
    _resolve_date_input,
)
from app.services.date_resolution_service import parse_reference_datetime
from app.services.google_calendar_service import GoogleCalendarService

logger = logging.getLogger(__name__)

DIAS_SEMANA_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


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
        timezone_str: str = "America/Bogota",
        slot_duration_minutes: int = 30,
        buffer_minutes: int = 0,
        min_notice_minutes: int = 60,
        working_hours: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, Any]:
        start_date_str, _, temporal_resolution = _resolve_date_input(date_input, reference_datetime)
        target_date = date.fromisoformat(start_date_str)

        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = ZoneInfo("America/Bogota")

        ref_now = parse_reference_datetime(reference_datetime)
        if ref_now.tzinfo is None:
            ref_now = ref_now.replace(tzinfo=tz)
        else:
            ref_now = ref_now.astimezone(tz)

        # Default working hours Monday-Friday 08:00 - 18:00, Saturday 08:00 - 13:00
        # weekdays: 0=Monday, 6=Sunday
        weekday_idx = target_date.weekday()
        if working_hours is None:
            working_hours = {
                "weekday": ("08:00", "18:00"),
                "saturday": ("08:00", "13:00"),
            }

        if weekday_idx == 6:  # Sunday
            day_hours = None
        elif weekday_idx == 5:  # Saturday
            day_hours = working_hours.get("saturday")
        else:
            day_hours = working_hours.get("weekday", ("08:00", "18:00"))

        if not day_hours:
            return self._empty_response(
                target_date_str=start_date_str,
                jornada=jornada,
                ref_now=ref_now,
                temporal_resolution=temporal_resolution,
                reason="Día no laborable",
            )

        start_time_parts = [int(p) for p in day_hours[0].split(":")]
        end_time_parts = [int(p) for p in day_hours[1].split(":")]
        day_start_local = datetime.combine(target_date, time(start_time_parts[0], start_time_parts[1]), tzinfo=tz)
        day_end_local = datetime.combine(target_date, time(end_time_parts[0], end_time_parts[1]), tzinfo=tz)

        day_start_utc = day_start_local.astimezone(UTC)
        day_end_utc = day_end_local.astimezone(UTC)

        # 1. Fetch busy intervals from Google Calendars (is_blocking=True)
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

        busy_intervals: list[tuple[datetime, datetime]] = []

        # Group blocking calendars by connection to minimize freebusy calls
        cals_by_connection: dict[str, list[TenantGoogleCalendar]] = {}
        for cal in blocking_cals:
            cals_by_connection.setdefault(cal.connection_id, []).append(cal)

        for conn_id, cals in cals_by_connection.items():
            conn = self.db.get(TenantGoogleCalendarConnection, conn_id)
            if not conn:
                continue
            cal_ids = [c.google_calendar_id for c in cals]
            try:
                g_busy = self.google_calendar_service.get_freebusy_intervals(
                    connection=conn,
                    calendar_ids=cal_ids,
                    time_min=day_start_utc,
                    time_max=day_end_utc,
                )
                for item in g_busy:
                    busy_intervals.append((item["start"], item["end"]))
            except Exception as exc:
                logger.warning("Error fetching FreeBusy for connection %s: %s", conn_id, exc)

        # 2. Fetch busy intervals from CrmBooking
        crm_bookings = list(
            self.db.scalars(
                select(CrmBooking).where(
                    CrmBooking.tenant_id == tenant_id,
                    CrmBooking.status.in_(["pending", "confirmed", "scheduled", "accepted"]),
                    CrmBooking.start_at < day_end_utc,
                    CrmBooking.end_at > day_start_utc,
                )
            ).all()
        )
        for b in crm_bookings:
            end_at = b.end_at or (b.start_at + timedelta(minutes=b.duration_minutes or slot_duration_minutes))
            busy_intervals.append((b.start_at, end_at))

        # 3. Generate slots and filter against busy intervals + buffers + notice
        slots_raw: list[dict[str, str]] = []
        step_delta = timedelta(minutes=slot_duration_minutes)
        slot_delta = timedelta(minutes=slot_duration_minutes)
        buffer_delta = timedelta(minutes=buffer_minutes)
        min_notice_delta = timedelta(minutes=min_notice_minutes)
        earliest_allowed_utc = ref_now.astimezone(UTC) + min_notice_delta

        current_local = day_start_local
        while current_local + slot_delta <= day_end_local:
            slot_start_utc = current_local.astimezone(UTC)
            slot_end_utc = (current_local + slot_delta).astimezone(UTC)

            # Check min notice
            if slot_start_utc >= earliest_allowed_utc:
                # Check collision with busy intervals (considering buffer)
                collides = False
                for busy_start, busy_end in busy_intervals:
                    # An interval collides if slot_start < (busy_end + buffer) and (slot_end + buffer) > busy_start
                    if slot_start_utc < (busy_end + buffer_delta) and (slot_end_utc + buffer_delta) > busy_start:
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
