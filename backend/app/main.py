from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.services.voice_service import create_call_session, create_sip_call_via_pbx
from app.services.calcom_service import get_available_slots
from app.core.config import settings
import uvicorn

app = FastAPI(title="ServiGlobal AI Voice Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


import os
import httpx

# ... imports ...


class CreateCallRequest(BaseModel):
    agent_id: str | None = None
    system_prompt: str | None = None
    template_context: dict | None = None
    turnstile_token: str | None = None


async def verify_turnstile(token: str):
    secret_key = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret_key:
        print("WARNING: TURNSTILE_SECRET_KEY not set. Skipping verification.")
        return

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret_key, "response": token},
        )
        result = response.json()
        if not result.get("success"):
            raise HTTPException(status_code=400, detail="Invalid Turnstile token")


@app.post("/api/v1/calls")
async def create_call(request: CreateCallRequest):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)

    try:
        join_url = await create_call_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            template_context=request.template_context,
        )
        return {"joinUrl": join_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ─── Cal.com Availability ───────────────────────────────────────────────────

class AvailabilityRequest(BaseModel):
    date: str                   # Accepts "YYYY-MM-DD" or full ISO 8601 timestamp
    jornada: str | None = None  # 'mañana' (09:00–11:30) | 'tarde' (12:00–16:30) | None = all


@app.get("/api/v1/availability")
async def check_availability_get(date: str, jornada: str | None = None):
    """
    GET version for quick browser/curl testing.
    Examples:
      /api/v1/availability?date=2026-04-20
      /api/v1/availability?date=2026-04-20&jornada=mañana
      /api/v1/availability?date=2026-04-20&jornada=tarde
    """
    try:
        result = await get_available_slots(date, jornada)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}")


@app.post("/api/v1/availability")
async def check_availability(request: AvailabilityRequest):
    """
    Query Cal.com for available appointment slots on a given date and jornada.
    The voice agent sends { "date": "YYYY-MM-DD", "jornada": "mañana" | "tarde" | null }
    and receives a list of slots plus a voice-friendly summary string.
    """
    try:
        result = await get_available_slots(request.date, request.jornada)
        return result
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar disponibilidad: {str(e)}")


class CreateOutboundCallRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str
    agent_id: str | None = None
    schedule_time: str | None = None  # ISO 8601 string
    company: str | None = None
    industry: str | None = None
    useCase: str | None = None
    volume: str | None = None
    painPoint: str | None = None
    turnstile_token: str | None = None


@app.post("/api/v1/call-outbound")
async def create_outbound_call(request: CreateOutboundCallRequest):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)

    try:
        # Pass name/email as context if needed
        context = {"user_phone": request.phone}
        if request.name:
            context["user_name"] = request.name
        if request.email:
            context["user_email"] = request.email
        if request.company:
            context["user_company"] = request.company
        if request.industry:
            context["user_industry"] = request.industry
        if request.useCase:
            context["user_use_case"] = request.useCase
        if request.volume:
            context["user_volume"] = request.volume
        if request.painPoint:
            context["user_pain_point"] = request.painPoint

        if request.schedule_time:
            from app.services.voice_service import create_scheduled_sip_call_via_pbx

            result = await create_scheduled_sip_call_via_pbx(
                phone=request.phone,
                schedule_time=request.schedule_time,
                agent_id=request.agent_id,
                template_context=context if context else None,
            )
        else:
            result = await create_sip_call_via_pbx(
                phone=request.phone,
                agent_id=request.agent_id,
                template_context=context if context else None,
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
