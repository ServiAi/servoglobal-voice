from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

from app.api.endpoints import notifications
from app.api.endpoints import chatwoot_webhook
from app.api.endpoints import voice
from app.api.endpoints import calcom

app.include_router(notifications.router)
app.include_router(chatwoot_webhook.router)
app.include_router(voice.router)
app.include_router(calcom.router)

@app.get("/health")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
