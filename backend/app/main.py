from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.services.voice_service import create_call_session, create_sip_call_via_pbx
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


class CreateCallRequest(BaseModel):
    agent_id: str | None = None
    system_prompt: str | None = None
    template_context: dict | None = None


@app.post("/api/v1/calls")
async def create_call(request: CreateCallRequest):
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


@app.post("/api/v1/call-outbound")
async def create_outbound_call(request: CreateOutboundCallRequest):
    try:
        # Pass name/email as context if needed
        context = {}
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
