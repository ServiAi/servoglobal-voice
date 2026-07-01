from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.config import settings
from app.services.calcom_service import (
    CAL_HTTP_TIMEOUT_SECONDS,
    CalComConfigurationError,
    CalComInputError,
    CalComUpstreamError,
    SlotUnavailableError,
    _build_summary,
    _in_jornada,
    _is_booking_unavailable_response,
    _resolve_date_input,
)
from app.services.date_resolution_service import parse_reference_datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CalComClientConfig:
    api_key: str
    event_type_id: int | None = None
    event_type_slug: str | None = None
    username: str | None = None
    team_slug: str | None = None
    organization_slug: str | None = None
    timezone: str = "America/Bogota"
    language: str = "es"
    api_version: str = "2024-08-13"


def sanitize_calcom_error(value: str) -> str:
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"cal_[A-Za-z0-9._\-]+", "cal_[redacted]", cleaned)
    cleaned = re.sub(r"[\w.+-]+@[\w.-]+", "[email-redacted]", cleaned)
    return cleaned[:300]


class CalComClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.CALCOM_API_BASE_URL).rstrip("/")

    @classmethod
    def legacy(cls) -> tuple["CalComClient", CalComClientConfig]:
        if not settings.CAL_API_KEY:
            raise CalComConfigurationError("CAL_API_KEY no esta configurada en las variables de entorno.")
        event_type_id = int(settings.CAL_EVENT_TYPE_ID) if settings.CAL_EVENT_TYPE_ID else None
        return cls(), CalComClientConfig(
            api_key=settings.CAL_API_KEY,
            event_type_id=event_type_id,
            username=settings.CAL_USERNAME or None,
            timezone=settings.CAL_TIMEZONE,
            api_version=settings.CALCOM_API_VERSION,
        )

    def get_available_slots(
        self,
        config: CalComClientConfig,
        *,
        date_input: str,
        jornada: str | None = None,
        reference_datetime: str | None = None,
    ) -> dict:
        start_date, end_date, temporal_resolution = _resolve_date_input(date_input, reference_datetime)
        params: dict[str, Any] = {
            "start": start_date,
            "end": end_date,
            "timeZone": config.timezone,
        }
        if config.event_type_id:
            params["eventTypeId"] = config.event_type_id
        else:
            if config.event_type_slug:
                params["eventTypeSlug"] = config.event_type_slug
            if config.username:
                params["username"] = config.username
            if config.team_slug:
                params["teamSlug"] = config.team_slug
            if config.organization_slug:
                params["organizationSlug"] = config.organization_slug

        logger.info(
            "Cal.com availability provider=calcom event_type_id=%s date=%s jornada=%s",
            config.event_type_id,
            start_date,
            jornada,
        )
        response = httpx.get(f"{self.base_url}/slots", params=params, headers=self._headers(config), timeout=CAL_HTTP_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise CalComUpstreamError(f"Cal.com API error {response.status_code}: {sanitize_calcom_error(response.text)}")
        data = response.json()
        slots_raw: list[dict] = []
        if isinstance(data.get("data"), dict):
            for slot in data["data"].get(start_date, []):
                start_time = slot.get("start", "")
                if start_time:
                    time_part = start_time[11:16]
                    if _in_jornada(time_part, jornada):
                        slots_raw.append({"start": start_time, "time": time_part})
        elif isinstance(data.get("slots"), list):
            for slot in data["slots"]:
                start_time = slot.get("start_time", slot.get("startTime", slot.get("start", "")))
                if start_time:
                    time_part = start_time[11:16]
                    if _in_jornada(time_part, jornada):
                        slots_raw.append({"start": start_time, "time": time_part})
        now = parse_reference_datetime(reference_datetime)
        dias_semana_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        summary_slots = [{"start": slot.get("time", slot["start"])} for slot in slots_raw]
        return {
            "metadata_consulta": {
                "fecha_ejecucion": now.strftime("%Y-%m-%d %H:%M:%S"),
                "dia_semana": dias_semana_es[now.weekday()],
                "jornada_solicitada": jornada or "todas",
                "temporal_resolution": temporal_resolution,
            },
            "date": start_date,
            "jornada": jornada or "all",
            "available_slots": slots_raw,
            "summary": _build_summary(summary_slots, start_date, jornada),
        }

    def create_booking(self, config: CalComClientConfig, payload: dict[str, Any]) -> dict:
        logger.info(
            "Cal.com booking_create provider=calcom event_type_id=%s start=%s",
            payload.get("eventTypeId"),
            payload.get("start"),
        )
        response = httpx.post(f"{self.base_url}/bookings", json=payload, headers=self._headers(config), timeout=CAL_HTTP_TIMEOUT_SECONDS)
        if response.status_code not in (200, 201):
            if response.status_code == 400 and _is_booking_unavailable_response(response.text):
                raise SlotUnavailableError("El horario no esta disponible. Verifica disponibilidad nuevamente.")
            raise CalComUpstreamError(f"Cal.com API error {response.status_code}: {sanitize_calcom_error(response.text)}")
        return response.json()

    def get_booking(self, config: CalComClientConfig, booking_uid: str) -> dict:
        response = httpx.get(f"{self.base_url}/bookings/{booking_uid}", headers=self._headers(config), timeout=CAL_HTTP_TIMEOUT_SECONDS)
        if response.status_code != 200:
            raise CalComUpstreamError(f"Cal.com API error {response.status_code}: {sanitize_calcom_error(response.text)}")
        return response.json()

    def cancel_booking(self, config: CalComClientConfig, booking_uid: str) -> dict:
        raise NotImplementedError("Cal.com cancel booking is prepared for Sprint 2B.")

    def reschedule_booking(self, config: CalComClientConfig, booking_uid: str, start: datetime) -> dict:
        raise NotImplementedError("Cal.com reschedule booking is prepared for Sprint 2B.")

    def _headers(self, config: CalComClientConfig) -> dict[str, str]:
        if not config.api_key:
            raise CalComConfigurationError("Cal.com API key is not configured.")
        return {
            "Authorization": f"Bearer {config.api_key}",
            "cal-api-version": config.api_version,
            "Content-Type": "application/json",
        }


def parse_utc_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalComInputError("start must be a valid UTC ISO 8601 datetime.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise CalComInputError("start must be UTC ISO 8601.")
    return parsed.astimezone(UTC)
