from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.core.calcom_constants import CALCOM_API_VERSIONS, DEFAULT_CALCOM_API_VERSION
from app.core.config import settings
from app.core.scheduling_exceptions import (
    SchedulingAuthenticationError,
    SchedulingConflictError,
    SchedulingNotFoundError,
    SchedulingPermissionError,
    SchedulingUpstreamError,
    SchedulingValidationError,
)
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
CAL_SLOTS_API_VERSION = CALCOM_API_VERSIONS.get("slots", "2024-09-04")


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
    api_version: str = DEFAULT_CALCOM_API_VERSION


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

    # -------------------------------------------------------------------------
    # Internal HTTP request & response handler
    # -------------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        config: CalComClientConfig,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        api_version: str | None = None,
        action_name: str = "Cal.com operation",
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = self._headers(config, api_version=api_version)
        try:
            response = httpx.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=headers,
                timeout=CAL_HTTP_TIMEOUT_SECONDS,
            )
        except httpx.RequestError as exc:
            sanitized = sanitize_calcom_error(str(exc))
            raise SchedulingUpstreamError(f"Error de red al conectar con Cal.com ({action_name}): {sanitized}") from exc

        return self._handle_response(response, action_name)

    def _handle_response(self, response: httpx.Response, action_name: str) -> dict[str, Any]:
        if response.status_code in (200, 201):
            try:
                data = response.json()
                return data if isinstance(data, dict) else {"data": data}
            except Exception:
                return {"status": "success"}

        if response.status_code == 204:
            return {"status": "success"}

        sanitized_body = sanitize_calcom_error(response.text)

        if response.status_code == 401:
            raise SchedulingAuthenticationError(
                f"Credenciales Cal.com no válidas o expiradas ({action_name}): {sanitized_body}"
            )
        if response.status_code == 403:
            if "plan" in sanitized_body.lower() or "team" in sanitized_body.lower() or "organization" in sanitized_body.lower():
                raise SchedulingPermissionError(
                    "Esta cuenta de Cal.com no permite administrar equipos mediante la credencial conectada."
                )
            raise SchedulingPermissionError(
                f"Permiso denegado por Cal.com para {action_name}: {sanitized_body}"
            )
        if response.status_code == 404:
            raise SchedulingNotFoundError(f"Recurso no encontrado en Cal.com ({action_name}): {sanitized_body}")
        if response.status_code == 409:
            raise SchedulingConflictError(f"Conflicto en Cal.com ({action_name}): {sanitized_body}")
        if response.status_code in (400, 422):
            raise SchedulingValidationError(f"Error de validación en Cal.com ({action_name}): {sanitized_body}")

        raise SchedulingUpstreamError(f"Cal.com API error {response.status_code} ({action_name}): {sanitized_body}")

    # -------------------------------------------------------------------------
    # Identity & Discovery
    # -------------------------------------------------------------------------
    def get_current_user(self, config: CalComClientConfig) -> dict[str, Any]:
        result = self._request(
            "GET",
            "/me",
            config,
            api_version=CALCOM_API_VERSIONS.get("me", "2024-08-13"),
            action_name="Obtener usuario actual",
        )
        return result.get("data", result)

    def discover_account(self, config: CalComClientConfig) -> dict[str, Any]:
        """Discovers current user, organization, teams, and active resources from Cal.com API v2."""
        user_data = self.get_current_user(config)
        schedules_data = self.list_schedules(config)
        event_types_data = self.list_event_types(config)

        teams_data: list[dict[str, Any]] = []
        try:
            teams_data = self.list_teams(config)
        except (SchedulingPermissionError, SchedulingNotFoundError, SchedulingUpstreamError) as exc:
            logger.info("Cal.com teams discovery skipped (not supported by plan or permissions): %s", exc)

        return {
            "user": user_data,
            "schedules": schedules_data,
            "event_types": event_types_data,
            "teams": teams_data,
            "counts": {
                "schedules": len(schedules_data),
                "event_types": len(event_types_data),
                "teams": len(teams_data),
            },
        }

    # -------------------------------------------------------------------------
    # Schedules & Date Overrides
    # -------------------------------------------------------------------------
    def list_schedules(self, config: CalComClientConfig) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            "/schedules",
            config,
            api_version=CALCOM_API_VERSIONS.get("schedules", "2024-06-11"),
            action_name="Listar horarios",
        )
        data = result.get("data")
        if isinstance(data, list):
            return data
        if isinstance(result.get("schedules"), list):
            return result["schedules"]
        return []

    def get_schedule(self, config: CalComClientConfig, schedule_id: str | int) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"/schedules/{schedule_id}",
            config,
            api_version=CALCOM_API_VERSIONS.get("schedules", "2024-06-11"),
            action_name=f"Obtener horario {schedule_id}",
        )
        return result.get("data", result)

    def create_schedule(self, config: CalComClientConfig, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/schedules",
            config,
            json=payload,
            api_version=CALCOM_API_VERSIONS.get("schedules", "2024-06-11"),
            action_name="Crear horario",
        )
        return result.get("data", result)

    def update_schedule(self, config: CalComClientConfig, schedule_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "PATCH",
            f"/schedules/{schedule_id}",
            config,
            json=payload,
            api_version=CALCOM_API_VERSIONS.get("schedules", "2024-06-11"),
            action_name=f"Actualizar horario {schedule_id}",
        )
        return result.get("data", result)

    def delete_schedule(self, config: CalComClientConfig, schedule_id: str | int) -> bool:
        self._request(
            "DELETE",
            f"/schedules/{schedule_id}",
            config,
            api_version=CALCOM_API_VERSIONS.get("schedules", "2024-06-11"),
            action_name=f"Eliminar horario {schedule_id}",
        )
        return True

    # -------------------------------------------------------------------------
    # Event Types
    # -------------------------------------------------------------------------
    def list_event_types(self, config: CalComClientConfig) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            "/event-types",
            config,
            api_version=CALCOM_API_VERSIONS.get("event_types", "2024-06-14"),
            action_name="Listar tipos de evento",
        )
        data = result.get("data")
        if isinstance(data, list):
            return data
        if isinstance(result.get("eventTypes"), list):
            return result["eventTypes"]
        return []

    def get_event_type(self, config: CalComClientConfig, event_type_id: str | int) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"/event-types/{event_type_id}",
            config,
            api_version=CALCOM_API_VERSIONS.get("event_types", "2024-06-14"),
            action_name=f"Obtener tipo de evento {event_type_id}",
        )
        return result.get("data", result)

    def create_event_type(self, config: CalComClientConfig, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/event-types",
            config,
            json=payload,
            api_version=CALCOM_API_VERSIONS.get("event_types", "2024-06-14"),
            action_name="Crear tipo de evento",
        )
        return result.get("data", result)

    def update_event_type(self, config: CalComClientConfig, event_type_id: str | int, payload: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "PATCH",
            f"/event-types/{event_type_id}",
            config,
            json=payload,
            api_version=CALCOM_API_VERSIONS.get("event_types", "2024-06-14"),
            action_name=f"Actualizar tipo de evento {event_type_id}",
        )
        return result.get("data", result)

    def delete_event_type(self, config: CalComClientConfig, event_type_id: str | int) -> bool:
        self._request(
            "DELETE",
            f"/event-types/{event_type_id}",
            config,
            api_version=CALCOM_API_VERSIONS.get("event_types", "2024-06-14"),
            action_name=f"Eliminar tipo de evento {event_type_id}",
        )
        return True

    # -------------------------------------------------------------------------
    # Teams & Memberships
    # -------------------------------------------------------------------------
    def list_teams(self, config: CalComClientConfig) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            "/teams",
            config,
            api_version=CALCOM_API_VERSIONS.get("teams", "2024-08-13"),
            action_name="Listar equipos",
        )
        data = result.get("data")
        if isinstance(data, list):
            return data
        if isinstance(result.get("teams"), list):
            return result["teams"]
        return []

    def get_team(self, config: CalComClientConfig, team_id: str | int) -> dict[str, Any]:
        result = self._request(
            "GET",
            f"/teams/{team_id}",
            config,
            api_version=CALCOM_API_VERSIONS.get("teams", "2024-08-13"),
            action_name=f"Obtener equipo {team_id}",
        )
        return result.get("data", result)

    def list_team_members(self, config: CalComClientConfig, team_id: str | int) -> list[dict[str, Any]]:
        result = self._request(
            "GET",
            f"/teams/{team_id}/memberships",
            config,
            api_version=CALCOM_API_VERSIONS.get("memberships", "2024-08-13"),
            action_name=f"Listar miembros de equipo {team_id}",
        )
        data = result.get("data")
        if isinstance(data, list):
            return data
        if isinstance(result.get("memberships"), list):
            return result["memberships"]
        return []

    # -------------------------------------------------------------------------
    # Slots & Bookings (Runtime)
    # -------------------------------------------------------------------------
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
        response = httpx.get(
            f"{self.base_url}/slots",
            params=params,
            headers=self._headers(config, api_version=CAL_SLOTS_API_VERSION),
            timeout=CAL_HTTP_TIMEOUT_SECONDS,
        )
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

    def cancel_booking(self, config: CalComClientConfig, booking_uid: str, payload: dict | None = None) -> dict:
        if not booking_uid:
            raise CalComInputError("booking_uid is required.")
        cancel_payload = {
            "cancellationReason": "Cancelado desde CRM",
            "cancelSubsequentBookings": False,
            **(payload or {}),
        }
        response = httpx.post(
            f"{self.base_url}/bookings/{booking_uid}/cancel",
            json=cancel_payload,
            headers=self._headers(config),
            timeout=CAL_HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code not in (200, 201):
            raise CalComUpstreamError(f"Cal.com API error {response.status_code}: {sanitize_calcom_error(response.text)}")
        return response.json()

    def reschedule_booking(self, config: CalComClientConfig, booking_uid: str, start: str, payload: dict | None = None) -> dict:
        if not booking_uid:
            raise CalComInputError("booking_uid is required.")
        if not start:
            raise CalComInputError("start is required for reschedule.")
        reschedule_payload = {
            "start": start,
            **(payload or {}),
        }
        response = httpx.post(
            f"{self.base_url}/bookings/{booking_uid}/reschedule",
            json=reschedule_payload,
            headers=self._headers(config),
            timeout=CAL_HTTP_TIMEOUT_SECONDS,
        )
        if response.status_code not in (200, 201):
            raise CalComUpstreamError(f"Cal.com API error {response.status_code}: {sanitize_calcom_error(response.text)}")
        return response.json()

    def _headers(self, config: CalComClientConfig, *, api_version: str | None = None) -> dict[str, str]:
        if not config.api_key:
            raise CalComConfigurationError("Cal.com API key is not configured.")
        return {
            "Authorization": f"Bearer {config.api_key}",
            "cal-api-version": api_version or config.api_version,
            "Content-Type": "application/json",
        }


def parse_utc_start(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalComInputError("start must be a valid UTC ISO 8601 datetime.") from exc
    if parsed.tzinfo is None:
        raise CalComInputError("start must include timezone information.")
    return parsed.astimezone(UTC)
