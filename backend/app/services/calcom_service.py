"""
calcom_service.py
Handles all communication with the Cal.com v2 API to fetch available slots.
"""

import httpx
import logging
from datetime import date, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)

CAL_API_BASE = "https://api.cal.com/v2"
CAL_API_VERSION_HEADER = "2024-09-04"

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
    parsed = date.fromisoformat(day_str)
    end_str = (parsed + timedelta(days=1)).isoformat()
    return day_str, end_str


async def get_available_slots(date_input: str, jornada: str | None = None) -> dict:
    """
    Query Cal.com for available slots on the given date, optionally filtered by jornada.

    Args:
        date_input: Date string in 'YYYY-MM-DD' or ISO 8601 format.
        jornada:    'mañana' (09:00–11:30), 'tarde' (12:00–16:30), or None for all.

    Returns:
        dict with keys: date, jornada, available_slots (list), summary (str)
    """
    start_date, end_date = _parse_date(date_input)

    if not settings.CAL_API_KEY:
        raise ValueError("CAL_API_KEY no está configurada en las variables de entorno.")

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

    logger.info(f"[Cal.com] GET {CAL_API_BASE}/slots | params={params} | jornada={jornada}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{CAL_API_BASE}/slots",
            params=params,
            headers=headers,
        )

    logger.info(f"[Cal.com] Response {response.status_code}: {response.text[:300]}")

    if response.status_code != 200:
        raise ValueError(
            f"Cal.com API error {response.status_code}: {response.text}"
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

    from datetime import datetime
    import locale

    # Obtener el timestamp actual
    ahora = datetime.now()
    
    # Mapeo manual de días en lugar de depender del locale del sistema
    dias_semana_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    nombre_dia = dias_semana_es[ahora.weekday()]

    return {
        "metadata_consulta": {
            "fecha_ejecucion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "dia_semana": nombre_dia,
            "jornada_solicitada": jornada or "todas"
        },
        "date": start_date,
        "jornada": jornada or "all",
        "available_slots": slots_raw,
        "summary": summary,
    }
