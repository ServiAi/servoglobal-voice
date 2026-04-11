from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.voice_service import create_call_session, create_sip_call_via_pbx
from app.services.notification_service import notification_service
from app.api.deps import verify_turnstile

router = APIRouter(prefix="/api/v1", tags=["Voice"])

class CreateCallRequest(BaseModel):
    agent_id: str | None = None
    system_prompt: str | None = None
    template_context: dict | None = None
    turnstile_token: str | None = None

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

@router.post("/calls")
async def create_call(request: CreateCallRequest):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)

    from datetime import datetime
    import pytz
    
    bogota_tz = pytz.timezone('America/Bogota')
    ahora = datetime.now(bogota_tz)
    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    
    context = request.template_context or {}
    context["fecha_ejecucion"] = ahora.strftime("%Y-%m-%d %H:%M:%S")
    context["dia_semana"] = dias_es[ahora.weekday()]

    try:
        join_url = await create_call_session(
            agent_id=request.agent_id,
            system_prompt=request.system_prompt,
            template_context=context,
        )
        
        # Registrar el inicio de la demo en el CRM
        if context:
            await notification_service.notify_demo_start(context)

        return {"joinUrl": join_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/call-outbound")
async def create_outbound_call(request: CreateOutboundCallRequest):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)

    try:
        from datetime import datetime
        import pytz
        
        bogota_tz = pytz.timezone('America/Bogota')
        ahora = datetime.now(bogota_tz)
        dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

        # Pass name/email/date as context
        context = {
            "user_phone": request.phone,
            "fecha_ejecucion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "dia_semana": dias_es[ahora.weekday()]
        }
        
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
                template_context=context,
            )
        else:
            result = await create_sip_call_via_pbx(
                phone=request.phone,
                agent_id=request.agent_id,
                template_context=context if context else None,
            )
            
        # Registrar el inicio de la demo en el CRM
        await notification_service.notify_demo_start(context)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
