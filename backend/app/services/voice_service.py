import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) <= 4:
        return "***"
    return f"***{digits[-4:]}"


def _ultravox_tenant_metadata() -> dict[str, str]:
    tenant_slug = (settings.BOOTSTRAP_TENANT_SLUG or "").strip()
    if not tenant_slug:
        raise ValueError("BOOTSTRAP_TENANT_SLUG is required to create Ultravox calls.")
    return {"tenant_slug": tenant_slug}


def _ultravox_call_metadata(template_context: dict | None = None) -> dict[str, str]:
    metadata = _ultravox_tenant_metadata()
    if isinstance(template_context, dict):
        context_id = template_context.get("context_id") or template_context.get("crm_context_id")
        form_submission_id = template_context.get("form_submission_id") or template_context.get("submission_id")
        if context_id:
            metadata["context_id"] = str(context_id)
            metadata["crm_context_id"] = str(context_id)
        if form_submission_id:
            metadata["form_submission_id"] = str(form_submission_id)
    return metadata


async def create_call_session(
    agent_id: str | None = None,
    system_prompt: str | None = None,
    template_context: dict | None = None,
) -> str:
    """
    Creates a call session with Ultravox and returns the joinUrl.
    """
    url = "https://api.ultravox.ai/api/calls"
    headers = {
        "X-API-Key": settings.ULTRAVOX_API_KEY,
        "Content-Type": "application/json",
    }

    # Determine Agent ID: Argument overrides Settings
    final_agent_id = agent_id or settings.DEFAULT_AGENT_ID

    payload = {
        "metadata": _ultravox_call_metadata(template_context),
    }

    if not final_agent_id:
        raise ValueError(
            "Agent ID is required. Please set DEFAULT_AGENT_ID in your .env file or pass it directly."
        )

    # Correct Endpoint for Agents:
    url = f"https://api.ultravox.ai/api/agents/{final_agent_id}/calls"

    # Add template context if provided
    if template_context:
        payload["templateContext"] = template_context

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url, json=payload, headers=headers, timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            return data["joinUrl"]
    except httpx.HTTPStatusError as e:
        response_text = e.response.text[:500]
        error_msg = f"Ultravox API error: {response_text}. AgentID: {final_agent_id}"
        logger.error("Ultravox API error: %s | AgentID: %s", response_text, final_agent_id)
        raise Exception(error_msg)
    except Exception as e:
        logger.error(f"Unexpected error creating call: {e}")
        raise


def normalize_e164_colombia(phone: str) -> str:
    """
    Normalizes a Colombian phone number to E.164 format (digits only, typically starts with 57).
    """
    import re

    digits = re.sub(r"\D", "", phone)

    # If 10 digits starting with 3 (e.g. 3001234567), 
    if len(digits) == 10 and digits.startswith("3"):
        return f"57{digits}"
    # If already has 57 (12 digits), return as is
    if len(digits) == 12 and digits.startswith("57"):
        return digits

    # Fallback: return digits (might be fixed line or international not handled)
    return digits


async def create_sip_call_via_pbx(
    phone: str,
    agent_id: str | None = None,
    template_context: dict | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> dict:
    """
    Crea una llamada en Ultravox que marque por SIP hacia tu Asterisk,
    y Asterisk luego enruta a PSTN por ialab-out.
    """
    final_agent_id = agent_id or settings.DEFAULT_AGENT_ID
    if not final_agent_id:
        raise ValueError("Agent ID requerido (DEFAULT_AGENT_ID o parámetro).")

    headers = {
        "X-API-Key": settings.ULTRAVOX_API_KEY,
        "Content-Type": "application/json",
    }

    number = normalize_e164_colombia(phone)

    # IMPORTANTE:
    # Decide si tu dialplan matchea con + o sin +.
    # Yo recomiendo mandar con +, y en Asterisk soportar ambos.
    dialed = f"+{number}"

    # Tu Asterisk público (IP o dominio).
    pbx_uri = f"sip:{dialed}@{settings.ASTERISK_PUBLIC_HOST}:5060"

    payload = {
        "medium": {
            "sip": {
                "outgoing": {
                    "to": pbx_uri,
                    "username": settings.UVX_SIP_USERNAME,
                    "password": settings.UVX_SIP_PASSWORD,
                }
            }
        },
        "firstSpeakerSettings": {"agent": {}},  # Force agent to speak first
        "metadata": _ultravox_call_metadata(template_context),
    }

    if template_context:
        payload["templateContext"] = template_context
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    if model:
        payload["model"] = model
    if voice:
        payload["voice"] = voice
    url = f"https://api.ultravox.ai/api/agents/{final_agent_id}/calls"

    context = template_context or {}
    safe_context_id = context.get("context_id") or context.get("crm_context_id")
    safe_form_submission_id = context.get("form_submission_id") or context.get("submission_id")

    logger.info(
        "Creating Ultravox SIP call via PBX | agent_id=%s | phone_tail=%s | has_context_id=%s | has_form_submission_id=%s",
        final_agent_id,
        _mask_phone(phone),
        bool(safe_context_id),
        bool(safe_form_submission_id),
    )

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers, timeout=20.0)
            r.raise_for_status()
            return r.json()  # normalmente te devuelve callId/estado
    except httpx.HTTPStatusError as e:
        response_text = e.response.text[:500]
        logger.error(
            "Ultravox API error creating SIP call | status=%s | response=%s",
            e.response.status_code,
            response_text,
        )
        raise


async def create_scheduled_sip_call_via_pbx(
    phone: str,
    schedule_time: str,
    agent_id: str | None = None,
    template_context: dict | None = None,
    system_prompt: str | None = None,
    model: str | None = None,
    voice: str | None = None,
) -> dict:
    """
    Creates a scheduled call batch in Ultravox.
    schedule_time: ISO 8601 string (e.g., "2023-11-07T05:31:56Z")
    """
    final_agent_id = agent_id or settings.DEFAULT_AGENT_ID
    if not final_agent_id:
        raise ValueError("Agent ID required (DEFAULT_AGENT_ID or parameter).")

    headers = {
        "X-API-Key": settings.ULTRAVOX_API_KEY,
        "Content-Type": "application/json",
    }

    # Normalize phone and construct SIP URI (reused from existing logic)
    number = normalize_e164_colombia(phone)
    dialed = f"+{number}"
    pbx_uri = f"sip:{dialed}@{settings.ASTERISK_PUBLIC_HOST}:5060"

    # Define the call object (same structure as immediate call's medium)
    call_config = {
        "medium": {
            "sip": {
                "outgoing": {
                    "to": pbx_uri,
                    "username": settings.UVX_SIP_USERNAME,
                    "password": settings.UVX_SIP_PASSWORD,
                }
            }
        },
        "firstSpeakerSettings": {"agent": {}},
        "metadata": _ultravox_call_metadata(template_context),
    }

    if template_context:
        call_config["templateContext"] = template_context
    if system_prompt:
        call_config["systemPrompt"] = system_prompt
    if model:
        call_config["model"] = model
    if voice:
        call_config["voice"] = voice

    # Calculate windowEnd (e.g., start time + 1 hour)
    from datetime import datetime, timedelta

    try:
        dt_start = datetime.fromisoformat(schedule_time.replace("Z", "+00:00"))
        dt_end = dt_start + timedelta(hours=1)
        window_end = dt_end.isoformat()
    except ValueError:
        # Fallback if parsing fails (though frontend sends ISO)
        window_end = schedule_time

    payload = {
        "windowStart": schedule_time,
        "windowEnd": window_end,
        "calls": [call_config],
    }
    url = f"https://api.ultravox.ai/api/agents/{final_agent_id}/scheduled_batches"

    context = template_context or {}
    safe_context_id = context.get("context_id") or context.get("crm_context_id")
    safe_form_submission_id = context.get("form_submission_id") or context.get("submission_id")

    logger.info(
        "Creating scheduled Ultravox SIP call via PBX | agent_id=%s | schedule_time=%s | phone_tail=%s | has_context_id=%s | has_form_submission_id=%s",
        final_agent_id,
        schedule_time,
        _mask_phone(phone),
        bool(safe_context_id),
        bool(safe_form_submission_id),
    )

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, headers=headers, timeout=20.0)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        response_text = e.response.text[:500]
        logger.error(
            "Ultravox API Batch error creating scheduled SIP call | status=%s | response=%s",
            e.response.status_code,
            response_text,
        )
        raise
