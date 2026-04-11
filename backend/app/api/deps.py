from fastapi import HTTPException
import httpx
from app.core.config import settings

async def verify_turnstile(token: str):
    secret_key = settings.TURNSTILE_SECRET_KEY
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
