from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from app.services.calcom_service import get_available_slots, create_booking
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Cal.com"])

class AvailabilityRequest(BaseModel):
    date: str                   # Accepts "YYYY-MM-DD" or full ISO 8601 timestamp
    jornada: str | None = None  # 'mañana' (09:00–11:30) | 'tarde' (12:00–16:30) | None = all

class CreateBookingRequest(BaseModel):
    date_str: str
    time_str: str
    name: str
    email: str
    phone: str | None = None

@router.get("/availability")
async def check_availability_get(date: str, jornada: str | None = None):
    try:
        result = await get_available_slots(date, jornada)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}")


@router.post("/availability")
async def check_availability(request: AvailabilityRequest):
    try:
        result = await get_available_slots(request.date, request.jornada)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}")

@router.post("/bookings")
async def create_new_booking(request: CreateBookingRequest):
    try:
        result = await create_booking(
            date_str=request.date_str,
            time_str=request.time_str,
            name=request.name,
            email=request.email,
            phone=request.phone,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear reserva: {str(e)}")


# ── Webhook Nativo de Cal.com ────────────────────────────────────────────────

MESES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}
DIAS = {
    0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
    4: "Viernes", 5: "Sábado", 6: "Domingo"
}

def format_calcom_datetime(iso_string: str) -> tuple[str, str]:
    """Convierte ISO 8601 UTC a la hora de Colombia con el formato amigable de Serviglobal."""
    # Reemplazamos 'Z' para compatibilidad con fromisoformat()
    dt_utc = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
    # Convertimos a hora local Colombia
    dt_bogota = dt_utc.astimezone(ZoneInfo("America/Bogota"))
    
    dia_semana = DIAS[dt_bogota.weekday()]
    mes = MESES[dt_bogota.month]
    date_str = f"{dia_semana} {dt_bogota.day} de {mes} de {dt_bogota.year}"
    time_str = dt_bogota.strftime("%I:%M %p").lstrip("0")
    
    return date_str, time_str

@router.post("/calcom/webhook")
async def receive_calcom_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Recibe el Webhook nativo desde Cal.com. 
    Intercepta el evento BOOKING_CREATED y envía las notificaciones y notas al CRM de Chatwoot.
    """
    from app.services.notification_service import notification_service

    try:
        payload_data = await request.json()
        logger.debug(f"[Cal.com] Webhook recibido: {payload_data.get('triggerEvent')}")

        if payload_data.get("triggerEvent") == "BOOKING_CREATED":
            payload = payload_data.get("payload", {})
            
            # Extraer datos de los asistentes / respuestas
            attendees = payload.get("attendees", [])
            responses = payload.get("responses", {})
            
            # Nombre y email preferimos sacarlos del primer attendee o responses
            client_name = responses.get("name") or (attendees[0].get("name") if attendees else "Desconocido")
            client_email = responses.get("email") or (attendees[0].get("email") if attendees else "")
            
            # Teléfono generalmente está en las respuestas
            client_phone = responses.get("phone") or ""
            
            start_time_iso = payload.get("startTime")
            if not start_time_iso or not client_phone:
                logger.warning("[Cal.com] Faltan datos críticos (startTime o phone) ignorando.")
                return {"status": "ignored", "reason": "missing_data"}

            try:
                date_str, time_str = format_calcom_datetime(start_time_iso)
            except Exception as e:
                logger.error(f"[Cal.com] Error parseando fecha {start_time_iso}: {e}")
                date_str, time_str = "Fecha", "Hora"

            logger.info(f"[Cal.com] Agendamiento recibido. Cliente: {client_name}, {date_str} {time_str}. Tel: {client_phone}")

            # Lanzamos la notificación en background para que Cal.com reciba el OK rápidamente (200)
            background_tasks.add_task(
                notification_service.notify_new_booking,
                client_phone=client_phone,
                client_name=client_name,
                date_str=date_str,
                time_str=time_str,
                client_email=client_email
            )
            
            return {"status": "processing_notifications"}
        else:
            return {"status": "ignored", "reason": "not_booking_created"}

    except Exception as e:
        logger.error(f"[Cal.com] Error procesando webhook: {e}")
        # Retornamos 200 igual para que Cal.com no reintente con errores de parseo
        return {"status": "error", "detail": str(e)}
