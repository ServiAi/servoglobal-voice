from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
import uvicorn
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="ServiGlobal AI Voice Backend")


def _cors_origins() -> list[str]:
    return [
        origin.strip().rstrip("/")
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.endpoints import notifications
from app.api.endpoints import chatwoot_webhook
from app.api.endpoints import voice
from app.api.endpoints import calcom
from app.api.endpoints import dashboard
from app.api.endpoints import me
from app.api.endpoints import ultravox_webhook
from app.api.endpoints.admin import tenants as admin_tenants
from app.api.endpoints import auth0 as auth0_endpoint
from app.api.endpoints import crm

app.include_router(notifications.router)
app.include_router(chatwoot_webhook.router)
app.include_router(voice.router)
app.include_router(calcom.router)
app.include_router(dashboard.router)
app.include_router(me.router)
app.include_router(ultravox_webhook.router)
app.include_router(admin_tenants.router)
app.include_router(auth0_endpoint.router)
app.include_router(crm.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
