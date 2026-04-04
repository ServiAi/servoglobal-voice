from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Header, status
from pydantic import BaseModel
import hmac
import hashlib
import os
from app.services.calcom_service import get_available_slots, create_booking
from datetime import datetime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Cal.com"])


class AvailabilityRequest(BaseModel):
    date: str  # Accepts "YYYY-MM-DD" or full ISO 8601 timestamp
    jornada: str | None = (
        None  # 'mañana' (09:00–11:30) | 'tarde' (12:00–16:30) | None = all
    )


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
        raise HTTPException(
            status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}"
        )


@router.post("/availability")
async def check_availability(request: AvailabilityRequest):
    try:
        result = await get_available_slots(request.date, request.jornada)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}"
        )


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
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}
DIAS = {
    0: "Lunes",
    1: "Martes",
    2: "Miércoles",
    3: "Jueves",
    4: "Viernes",
    5: "Sábado",
    6: "Domingo",
}


def format_calcom_datetime(iso_string: str) -> tuple[str, str]:
    """Convierte ISO 8601 UTC a la hora de Colombia con el formato amigable de Serviglobal."""
    # Reemplazamos 'Z' para compatibilidad con fromisoformat()
    dt_utc = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    # Convertimos a hora local Colombia
    dt_bogota = dt_utc.astimezone(ZoneInfo("America/Bogota"))

    dia_semana = DIAS[dt_bogota.weekday()]
    mes = MESES[dt_bogota.month]
    date_str = f"{dia_semana} {dt_bogota.day} de {mes} de {dt_bogota.year}"
    time_str = dt_bogota.strftime("%I:%M %p").lstrip("0")

    return date_str, time_str


@router.post("/calcom/webhook")
async def receive_calcom_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_cal_signature_256: str | None = Header(None)
):
    """
    Recibe el Webhook nativo desde Cal.com.
    Intercepta el evento BOOKING_CREATED y envía las notificaciones y notas al CRM de Chatwoot.
    """
    from app.services.notification_service import notification_service

    # --- VALIDACIÓN CRIPTOGRÁFICA DE SEGURIDAD (Bypass BFM) ---
    calcom_secret = os.getenv("CALCOM_WEBHOOK_SECRET")
    
    if calcom_secret:
        if not x_cal_signature_256:
            logger.warning("[Cal.com] Rechazado: Falta la firma X-Cal-Signature-256")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing cryptographic signature"
            )

        raw_body = await request.body()
        expected_signature = hmac.new(
            key=calcom_secret.encode('utf-8'),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, x_cal_signature_256):
            logger.warning("[Cal.com] Rechazado: Firma HMAC de webhook inválida")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid signature integrity"
            )
    else:
        logger.warning("[Cal.com] SEGURO INACTIVO: CALCOM_WEBHOOK_SECRET no configurado en entorno.")

    try:
        payload_data = await request.json()
        logger.debug(f"[Cal.com] Webhook recibido: {payload_data.get('triggerEvent')}")

        if payload_data.get("triggerEvent") == "BOOKING_CREATED":
            payload = payload_data.get("payload", {})

            # Extraer datos de los asistentes / respuestas
            attendees = payload.get("attendees", [])
            responses = payload.get("responses", {})

            # Nombre y email preferimos sacarlos del primer attendee o responses
            client_name = responses.get("name") or (
                attendees[0].get("name") if attendees else "Desconocido"
            )
            client_email = responses.get("email") or (
                attendees[0].get("email") if attendees else ""
            )

            # Teléfono generalmente está en las respuestas. Búsqueda robusta:
            client_phone = responses.get("phone") or ""
            if not client_phone:
                # Buscar en todas las llaves de responses por si le cambiaron el ID al campo en Cal.com
                for key, val in responses.items():
                    if isinstance(val, str) and (
                        "phone" in key.lower()
                        or "tel" in key.lower()
                        or "cel" in key.lower()
                        or "+" in val
                    ):
                        client_phone = val
                        break

            start_time_iso = payload.get("startTime")
            if not start_time_iso or not client_phone:
                logger.warning(
                    f"[Cal.com] Faltan datos críticos (startTime o phone). Respuestas extraídas: {responses}"
                )
                return {"status": "ignored", "reason": "missing_data_or_no_phone"}

            try:
                date_str, time_str = format_calcom_datetime(start_time_iso)
            except Exception as e:
                logger.error(f"[Cal.com] Error parseando fecha {start_time_iso}: {e}")
                date_str, time_str = "Fecha", "Hora"

            logger.info(
                f"[Cal.com] Agendamiento recibido. Cliente: {client_name}, {date_str} {time_str}. Tel: {client_phone}"
            )

            # Lanzamos la notificación en background para que Cal.com reciba el OK rápidamente (200)
            background_tasks.add_task(
                notification_service.notify_new_booking,
                client_phone=client_phone,
                client_name=client_name,
                date_str=date_str,
                time_str=time_str,
                client_email=client_email,
            )

            return {"status": "processing_notifications"}
        else:
            return {"status": "ignored", "reason": "not_booking_created"}

    except Exception as e:
        logger.error(f"[Cal.com] Error procesando webhook: {e}")
        # Retornamos 200 igual para que Cal.com no reintente con errores de parseo
        return {"status": "error", "detail": str(e)}
