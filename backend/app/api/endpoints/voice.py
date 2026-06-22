from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.identity import Tenant
from app.services.crm_call_context_service import CrmCallContextService
from app.services.voice_service import create_call_session, create_sip_call_via_pbx
from app.services.notification_service import notification_service
from app.services.tenant_usage_service import TenantUsageService
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


def _bootstrap_tenant(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == settings.BOOTSTRAP_TENANT_SLUG))
    if tenant is None:
        raise HTTPException(status_code=400, detail="Bootstrap tenant not found")
    return tenant


def _external_call_id_from_result(result: dict) -> str | None:
    for key in ("callId", "call_id", "external_call_id", "id"):
        value = result.get(key)
        if value:
            return str(value)
    call = result.get("call")
    if isinstance(call, dict):
        for key in ("callId", "call_id", "external_call_id", "id"):
            value = call.get(key)
            if value:
                return str(value)
    return None

@router.post("/calls")
async def create_call(request: CreateCallRequest, db: Session = Depends(get_db)):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)
    TenantUsageService(db).ensure_tenant_can_start_call_by_slug(settings.BOOTSTRAP_TENANT_SLUG)
    tenant = _bootstrap_tenant(db)

    from datetime import datetime
    import pytz
    
    bogota_tz = pytz.timezone('America/Bogota')
    ahora = datetime.now(bogota_tz)
    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    
    context = request.template_context or {}
    context["fecha_ejecucion"] = ahora.strftime("%Y-%m-%d %H:%M:%S")
    context["dia_semana"] = dias_es[ahora.weekday()]
    call_context = CrmCallContextService(db).create_context(
        tenant.id,
        external_provider="ultravox",
        context=context,
    )
    context["context_id"] = call_context.context_id or call_context.id
    context["crm_context_id"] = call_context.context_id or call_context.id

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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/call-outbound")
async def create_outbound_call(request: CreateOutboundCallRequest, db: Session = Depends(get_db)):
    if not request.turnstile_token:
        raise HTTPException(status_code=400, detail="Turnstile token missing")

    await verify_turnstile(request.turnstile_token)
    TenantUsageService(db).ensure_tenant_can_start_call_by_slug(settings.BOOTSTRAP_TENANT_SLUG)
    tenant = _bootstrap_tenant(db)

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

        call_context = CrmCallContextService(db).create_context(
            tenant.id,
            external_provider="ultravox",
            context=context,
        )
        context["context_id"] = call_context.context_id or call_context.id
        context["crm_context_id"] = call_context.context_id or call_context.id

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

        external_call_id = _external_call_id_from_result(result)
        if external_call_id:
            CrmCallContextService(db).attach_external_call_id(
                tenant.id,
                call_context.id,
                external_call_id,
                external_provider="ultravox",
            )
            
        # Registrar el inicio de la demo en el CRM
        await notification_service.notify_demo_start(context)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
