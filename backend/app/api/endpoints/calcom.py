from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.calcom_service import get_available_slots, create_booking

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
