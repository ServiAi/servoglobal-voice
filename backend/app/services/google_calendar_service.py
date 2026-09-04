from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.integrations import TenantGoogleCalendar, TenantGoogleCalendarConnection
from app.services.google_calendar_oauth_service import GoogleCalendarOAuthService
from app.services.secret_manager_service import SecretManager

logger = logging.getLogger(__name__)


def sanitize_google_calendar_error(value: str) -> str:
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"(access_token|refresh_token|client_secret)[^,\s}]*", r"\1=[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned[:300]


class GoogleCalendarService:
    def __init__(
        self,
        db: Session | None = None,
        oauth_service: GoogleCalendarOAuthService | None = None,
        secret_manager: SecretManager | None = None,
    ) -> None:
        self.db = db
        self.secret_manager = secret_manager or SecretManager()
        self.oauth_service = oauth_service or (GoogleCalendarOAuthService(db, self.secret_manager) if db else None)

    def build_event_payload(
        self,
        *,
        summary: str,
        description: str | None,
        start_at: datetime,
        end_at: datetime,
        timezone: str,
        attendee_email: str | None = None,
        attendee_name: str | None = None,
        location: str | None = None,
        enable_meet: bool = True,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "summary": summary,
            "description": description or "",
            "start": {"dateTime": start_at.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_at.isoformat(), "timeZone": timezone},
        }
        if location:
            payload["location"] = location
        if attendee_email:
            att = {"email": attendee_email}
            if attendee_name:
                att["displayName"] = attendee_name
            payload["attendees"] = [att]
        if enable_meet:
            payload["conferenceData"] = {
                "createRequest": {
                    "requestId": f"meet-{int(start_at.timestamp())}-{start_at.strftime('%Y%m%d%H%M')}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            }
        return payload

    def sync_calendars(self, connection: TenantGoogleCalendarConnection) -> list[TenantGoogleCalendar]:
        if not self.db or not self.oauth_service:
            raise ValueError("Database session and OAuth service are required for calendar sync.")

        token = self.oauth_service.get_valid_access_token(connection)
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = httpx.get("https://www.googleapis.com/calendar/v3/users/me/calendarList", headers=headers, timeout=15.0)
        except Exception as exc:
            msg = sanitize_google_calendar_error(str(exc))
            connection.last_error_message = msg
            self.db.commit()
            raise ValueError(f"Failed to fetch calendarList from Google: {msg}") from exc

        if resp.status_code != 200:
            msg = sanitize_google_calendar_error(resp.text)
            connection.last_error_message = msg
            self.db.commit()
            raise ValueError(f"Google calendarList failed: {msg}")

        data = resp.json()
        items = data.get("items", [])
        synced: list[TenantGoogleCalendar] = []

        existing_cals = {
            cal.google_calendar_id: cal
            for cal in self.db.scalars(
                select(TenantGoogleCalendar).where(
                    TenantGoogleCalendar.tenant_id == connection.tenant_id,
                    TenantGoogleCalendar.connection_id == connection.id,
                )
            ).all()
        }

        has_destination = any(cal.is_booking_destination for cal in existing_cals.values())

        for item in items:
            g_cal_id = item.get("id")
            if not g_cal_id:
                continue
            is_primary = bool(item.get("primary", False))
            cal = existing_cals.get(g_cal_id)
            if not cal:
                cal = TenantGoogleCalendar(
                    tenant_id=connection.tenant_id,
                    connection_id=connection.id,
                    google_calendar_id=g_cal_id,
                    summary=item.get("summary"),
                    description=item.get("description"),
                    time_zone=item.get("timeZone"),
                    is_primary=is_primary,
                    is_blocking=True,
                    is_booking_destination=is_primary and not has_destination,
                    access_role=item.get("accessRole"),
                )
                self.db.add(cal)
                if cal.is_booking_destination:
                    has_destination = True
            else:
                cal.summary = item.get("summary")
                cal.description = item.get("description")
                cal.time_zone = item.get("timeZone")
                cal.is_primary = is_primary
                cal.access_role = item.get("accessRole")
                if is_primary and not has_destination:
                    cal.is_booking_destination = True
                    has_destination = True
            synced.append(cal)

        connection.last_sync_at = datetime.now(UTC)
        connection.last_error_message = None
        self.db.commit()
        for cal in synced:
            self.db.refresh(cal)
        return synced

    def list_tenant_calendars(self, tenant_id: str, connection_id: str | None = None) -> list[TenantGoogleCalendar]:
        if not self.db:
            raise ValueError("Database session is required.")
        stmt = select(TenantGoogleCalendar).where(TenantGoogleCalendar.tenant_id == tenant_id)
        if connection_id:
            stmt = stmt.where(TenantGoogleCalendar.connection_id == connection_id)
        return list(self.db.scalars(stmt.order_by(TenantGoogleCalendar.is_primary.desc(), TenantGoogleCalendar.created_at.asc())).all())

    def update_calendar_settings(
        self,
        *,
        tenant_id: str,
        calendar_id: str,
        is_blocking: bool | None = None,
        is_booking_destination: bool | None = None,
    ) -> TenantGoogleCalendar:
        if not self.db:
            raise ValueError("Database session is required.")
        cal = self.db.scalar(
            select(TenantGoogleCalendar).where(
                TenantGoogleCalendar.tenant_id == tenant_id,
                TenantGoogleCalendar.id == calendar_id,
            )
        )
        if not cal:
            raise ValueError("Calendar not found.")
        if is_blocking is not None:
            cal.is_blocking = is_blocking
        if is_booking_destination is not None:
            if is_booking_destination:
                # Clear other booking destinations for this connection
                for other in self.db.scalars(
                    select(TenantGoogleCalendar).where(
                        TenantGoogleCalendar.tenant_id == tenant_id,
                        TenantGoogleCalendar.connection_id == cal.connection_id,
                        TenantGoogleCalendar.id != cal.id,
                    )
                ).all():
                    other.is_booking_destination = False
            cal.is_booking_destination = is_booking_destination
        self.db.commit()
        self.db.refresh(cal)
        return cal

    def get_freebusy_intervals(
        self,
        connection: TenantGoogleCalendarConnection,
        calendar_ids: list[str],
        time_min: datetime,
        time_max: datetime,
    ) -> list[dict[str, datetime]]:
        if not self.oauth_service:
            raise ValueError("OAuth service is required for freeBusy lookup.")
        token = self.oauth_service.get_valid_access_token(connection)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": cid} for cid in calendar_ids],
        }
        try:
            resp = httpx.post("https://www.googleapis.com/calendar/v3/freeBusy", headers=headers, json=payload, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"FreeBusy request failed: {sanitize_google_calendar_error(str(exc))}") from exc

        if resp.status_code != 200:
            raise ValueError(f"Google FreeBusy API error: {sanitize_google_calendar_error(resp.text)}")

        data = resp.json()
        calendars_data = data.get("calendars", {})
        intervals: list[dict[str, datetime]] = []

        for cid, info in calendars_data.items():
            for busy in info.get("busy", []):
                try:
                    start_dt = datetime.fromisoformat(busy["start"]).astimezone(UTC)
                    end_dt = datetime.fromisoformat(busy["end"]).astimezone(UTC)
                    intervals.append({"start": start_dt, "end": end_dt})
                except Exception:
                    continue

        intervals.sort(key=lambda x: x["start"])
        return intervals

    def create_event(
        self,
        connection: TenantGoogleCalendarConnection | None,
        payload: dict[str, Any],
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        if connection is None or connection.status != "connected":
            raise ValueError("Google Calendar connection is not enabled or not connected.")
        if not self.oauth_service:
            raise ValueError("OAuth service is required to create an event.")

        token = self.oauth_service.get_valid_access_token(connection)
        target_cal = calendar_id or connection.calendar_id or "primary"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(target_cal, safe='')}/events?conferenceDataVersion=1"
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"Google create event network error: {sanitize_google_calendar_error(str(exc))}") from exc

        if resp.status_code not in (200, 201):
            raise ValueError(f"Google create event failed: {sanitize_google_calendar_error(resp.text)}")

        return resp.json()

    def patch_event(
        self,
        connection: TenantGoogleCalendarConnection | None,
        event_id: str,
        payload: dict[str, Any],
        calendar_id: str | None = None,
    ) -> dict[str, Any]:
        if connection is None or connection.status != "connected":
            raise ValueError("Google Calendar connection is not enabled or not connected.")
        if not self.oauth_service:
            raise ValueError("OAuth service is required to patch an event.")

        token = self.oauth_service.get_valid_access_token(connection)
        target_cal = calendar_id or connection.calendar_id or "primary"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(target_cal, safe='')}/events/{quote(event_id, safe='')}"
        try:
            resp = httpx.patch(url, headers=headers, json=payload, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"Google patch event network error: {sanitize_google_calendar_error(str(exc))}") from exc

        if resp.status_code != 200:
            raise ValueError(f"Google patch event failed: {sanitize_google_calendar_error(resp.text)}")

        return resp.json()

    def delete_event(
        self,
        connection: TenantGoogleCalendarConnection | None,
        event_id: str,
        calendar_id: str | None = None,
    ) -> bool:
        if connection is None or connection.status != "connected":
            raise ValueError("Google Calendar connection is not enabled or not connected.")
        if not self.oauth_service:
            raise ValueError("OAuth service is required to delete an event.")

        token = self.oauth_service.get_valid_access_token(connection)
        target_cal = calendar_id or connection.calendar_id or "primary"
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://www.googleapis.com/calendar/v3/calendars/{quote(target_cal, safe='')}/events/{quote(event_id, safe='')}"
        try:
            resp = httpx.delete(url, headers=headers, timeout=15.0)
        except Exception as exc:
            raise ValueError(f"Google delete event network error: {sanitize_google_calendar_error(str(exc))}") from exc

        if resp.status_code not in (200, 204):
            raise ValueError(f"Google delete event failed: {sanitize_google_calendar_error(resp.text)}")

        return True
