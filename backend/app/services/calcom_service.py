"""
calcom_service.py
Handles all communication with the Cal.com v2 API to fetch available slots.
"""

import httpx
import logging
import pytz
import re
from datetime import date, timedelta, datetime
from app.core.config import settings
from app.services.date_resolution_service import (
    is_iso_like_date,
    parse_reference_datetime,
    resolve_temporal_expression,
)
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)

CAL_API_BASE = settings.CALCOM_API_BASE_URL
CAL_API_VERSION_HEADER = settings.CALCOM_API_VERSION
CAL_HTTP_TIMEOUT_SECONDS = 8.0


def _sanitize_calcom_error(value: str) -> str:
    cleaned = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"cal_[A-Za-z0-9._\-]+", "cal_[redacted]", cleaned)
    cleaned = re.sub(r"[\w.+-]+@[\w.-]+", "[email-redacted]", cleaned)
    return cleaned[:300]


class CalComInputError(ValueError):
    """Expected user/tool input problem before calling Cal.com."""


class SlotUnavailableError(ValueError):
    """Requested booking time is not available according to Cal.com slots."""


class CalComConfigurationError(RuntimeError):
    """Server-side Cal.com configuration is missing or invalid."""


class CalComUpstreamError(RuntimeError):
    """Cal.com returned an unexpected error."""

# ─── Jornada definitions ─────────────────────────────────────────────────────
# mañana : 09:00 – 11:30
# tarde  : 12:00 – 16:30
JORNADA_RANGES = {
    "mañana": ("09:00", "11:30"),
    "manana":  ("09:00", "11:30"),   # alias without tilde
    "tarde":  ("12:00", "16:30"),
}


def _in_jornada(time_str: str, jornada: str | None) -> bool:
    """Return True if time_str (HH:MM) falls within the jornada range."""
    if not jornada:
        return True  # no filter → return all slots
    rng = JORNADA_RANGES.get(jornada.lower())
    if not rng:
        return True  # unknown jornada → return all slots
    return rng[0] <= time_str <= rng[1]


def _build_summary(slots: list[dict], input_date: str, jornada: str | None) -> str:
    """Generate a human-readable summary string for the voice agent to read aloud."""
    jornada_label = f" ({jornada})" if jornada else ""
    if not slots:
        return f"No hay horarios disponibles para el {input_date}{jornada_label}."

    times = [s["start"] for s in slots]
    if len(times) == 1:
        return f"Hay 1 horario disponible{jornada_label}: {times[0]}."
    elif len(times) == 2:
        return f"Hay 2 horarios disponibles{jornada_label}: {times[0]} y {times[1]}."
    else:
        joined = ", ".join(times[:-1]) + f" y {times[-1]}"
        return f"Hay {len(times)} horarios disponibles para la jornada {jornada_label}: {joined}."


def _parse_date(date_input: str) -> tuple[str, str]:
    """
    Accepts 'YYYY-MM-DD' or full ISO 8601 and returns (start_date, end_date)
    as 'YYYY-MM-DD' strings covering the requested day.
    """
    day_str = date_input[:10]
    try:
        parsed = date.fromisoformat(day_str)
    except ValueError as exc:
        raise CalComInputError(f"Fecha invalida para disponibilidad: {date_input}") from exc
    end_str = (parsed + timedelta(days=1)).isoformat()
    return day_str, end_str


def _resolve_date_input(
    date_input: str,
    reference_datetime: str | None = None,
) -> tuple[str, str, dict | None]:
    if is_iso_like_date(date_input):
        start_date, end_date = _parse_date(date_input)
        return start_date, end_date, None

    try:
        resolution = resolve_temporal_expression(
            expression=date_input,
            reference_datetime=reference_datetime,
        )
    except ValueError as exc:
        raise CalComInputError(str(exc)) from exc
    start_date, end_date = _parse_date(resolution.date)
    return start_date, end_date, resolution.as_dict()


def _normalize_time(time_input: str) -> str:
    raw_value = (time_input or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(raw_value, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise CalComInputError(f"Hora invalida para agendamiento: {time_input}")


def _is_booking_unavailable_response(response_text: str) -> bool:
    normalized = (response_text or "").lower()
    return (
        "not available" in normalized
        or "already has booking" in normalized
        or "no esta disponible" in normalized
        or "no está disponible" in normalized
    )


async def get_available_slots(
    date_input: str,
    jornada: str | None = None,
    reference_datetime: str | None = None,
) -> dict:
    """
    Query Cal.com for available slots on the given date, optionally filtered by jornada.

    Args:
        date_input: Date string in 'YYYY-MM-DD' or ISO 8601 format.
        jornada:    'mañana' (09:00–11:30), 'tarde' (12:00–16:30), or None for all.

    Returns:
        dict with keys: date, jornada, available_slots (list), summary (str)
    """
    start_date, end_date, temporal_resolution = _resolve_date_input(
        date_input,
        reference_datetime,
    )

    if not settings.CAL_API_KEY:
        raise CalComConfigurationError("CAL_API_KEY no esta configurada en las variables de entorno.")

    # NOTE: When using eventTypeId, do NOT include 'username' — they are mutually exclusive.
    params = {
        "eventTypeId": settings.CAL_EVENT_TYPE_ID,
        "start": start_date,
        "end": end_date,
        "timeZone": settings.CAL_TIMEZONE,
    }

    headers = {
        "Authorization": f"Bearer {settings.CAL_API_KEY}",
        "cal-api-version": CAL_API_VERSION_HEADER,
        "Content-Type": "application/json",
    }

    logger.info(
        "[Cal.com] GET slots provider=calcom event_type_id=%s start=%s end=%s jornada=%s",
        settings.CAL_EVENT_TYPE_ID,
        start_date,
        end_date,
        jornada,
    )

    async with httpx.AsyncClient(timeout=CAL_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(
            f"{CAL_API_BASE}/slots",
            params=params,
            headers=headers,
        )

    logger.info("[Cal.com] slots response status_code=%s", response.status_code)

    if response.status_code != 200:
        raise CalComUpstreamError(
            f"Cal.com API error {response.status_code}: {_sanitize_calcom_error(response.text)}"
        )

    data = response.json()

    # Cal.com v2 actual response: { "status": "success", "data": { "YYYY-MM-DD": [{start: ...}], ... } }
    # Dates are direct keys under "data", NOT nested under "slots".
    slots_raw = []

    if "data" in data and isinstance(data["data"], dict):
        # Filter only the requested day — Cal.com can return adjacent days too.
        slot_list = data["data"].get(start_date, [])
        for slot in slot_list:
            start_time = slot.get("start", "")  # "2026-04-20T09:00:00.000-05:00"
            if start_time:
                time_part = start_time[11:16]   # extract "HH:MM"
                if _in_jornada(time_part, jornada):
                    slots_raw.append({"start": time_part})

    # Fallback: flat { "slots": [...] } format
    elif "slots" in data:
        for slot in data["slots"]:
            start_time = slot.get("start_time", slot.get("startTime", slot.get("start", "")))
            if start_time:
                time_part = start_time[11:16]
                if _in_jornada(time_part, jornada):
                    slots_raw.append({"start": time_part})

    summary = _build_summary(slots_raw, start_date, jornada)

    import locale

    # Obtener el timestamp actual con zona horaria de Bogotá
    ahora = parse_reference_datetime(reference_datetime)
    
    # Mapeo manual de días en lugar de depender del locale del sistema
    dias_semana_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    nombre_dia = dias_semana_es[ahora.weekday()]

    return {
        "metadata_consulta": {
            "fecha_ejecucion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "dia_semana": nombre_dia,
            "jornada_solicitada": jornada or "todas",
            "temporal_resolution": temporal_resolution
        },
        "date": start_date,
        "jornada": jornada or "all",
        "available_slots": slots_raw,
        "summary": summary,
    }


async def create_booking(date_str: str, time_str: str, name: str, email: str, phone: str = None) -> dict:
    """
    Crea una nueva reserva en Cal.com usando la API v2.
    
    Args:
        date_str: Fecha en formato 'YYYY-MM-DD'
        time_str: Hora de inicio en formato 'HH:MM' (ej. '09:00')
        name: Nombre del asistente
        email: Correo del asistente
        phone: Teléfono del asistente (opcional)
        
    Returns:
        dict con el resultado de la reserva (status, data)
    """
    if not settings.CAL_API_KEY:
        raise CalComConfigurationError("CAL_API_KEY no esta configurada en las variables de entorno.")

    normalized_time = _normalize_time(time_str)
        
    # Ensure start_datetime is ISO 8601 with timezone
    tz = pytz.timezone(settings.CAL_TIMEZONE)
    try:
        base_dt = datetime.fromisoformat(f"{date_str}T{normalized_time}:00")
    except ValueError as exc:
        raise CalComInputError(
            f"Fecha u hora invalida para agendamiento: {date_str} {time_str}"
        ) from exc
    aware_dt = tz.localize(base_dt)
    start_datetime = aware_dt.isoformat()
    
    payload = {
        "eventTypeId": int(settings.CAL_EVENT_TYPE_ID) if settings.CAL_EVENT_TYPE_ID else 0,
        "start": start_datetime,
        "attendee": {
            "name": name,
            "email": email,
            "timeZone": settings.CAL_TIMEZONE,
            "language": "es"
        }
    }
    
    if phone:
        payload["attendee"]["phoneNumber"] = phone
        
    headers = {
        "Authorization": f"Bearer {settings.CAL_API_KEY}",
        "cal-api-version": "2024-08-13",  # Booking v2 operations require this specific version
        "Content-Type": "application/json"
    }
    
    logger.info("[Cal.com] POST bookings provider=calcom start=%s", start_datetime)
    
    async with httpx.AsyncClient(timeout=CAL_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{CAL_API_BASE}/bookings",
            json=payload,
            headers=headers
        )
        
    logger.info("[Cal.com] booking response status_code=%s", response.status_code)
    
    if response.status_code not in (200, 201):
        if response.status_code == 400 and _is_booking_unavailable_response(response.text):
            raise SlotUnavailableError(
                f"El horario {normalized_time} no esta disponible para {date_str}. "
                "Verifica disponibilidad nuevamente antes de crear el evento."
            )
        raise CalComUpstreamError(
            f"Cal.com API error {response.status_code} al crear reserva: {_sanitize_calcom_error(response.text)}"
        )
    result_data = response.json()

    # Las notificaciones al cliente y al equipo Serviglobal
    # ahora se envían exclusivamente a través del webhook de Cal.com (/calcom/webhook).
    # Se ha eliminado el envío duplicado desde aquí.

    return result_data
