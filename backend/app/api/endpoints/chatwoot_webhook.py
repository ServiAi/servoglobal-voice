from fastapi import APIRouter, Request, Header
from app.core.config import settings
from app.services.chatwoot_service import chatwoot_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chatwoot", tags=["Chatwoot Webhook"])


@router.post("/webhook")
async def chatwoot_webhook(request: Request):
    """
    Recibe eventos de Chatwoot (mensajes entrantes de WhatsApp, etc.)
    y ejecuta la lógica de IA para responder automáticamente.

    Chatwoot envía un POST con este formato:
    {
      "event": "message_created",
      "message_type": "incoming",   <- solo procesamos estos
      "content": "Hola, quiero info",
      "conversation": { "id": 123, "status": "open" },
      "contact": { "name": "Juan", "phone_number": "+573201234567" },
      "inbox": { "channel": "Channel::Whatsapp" }
    }
    """
    try:
        payload = await request.json() 
    except Exception:
        logger.warning("Chatwoot webhook: payload no es JSON válido")
        return {"status": "ignored"}

    event_type = payload.get("event")
    logger.info(f"Chatwoot webhook recibido: event={event_type}")

    # Solo procesar mensajes nuevos entrantes del cliente
    if event_type != "message_created":
        return {"status": "ignored", "reason": "not message_created"}

    message_type = payload.get("message_type")
    if message_type != "incoming":
        return {"status": "ignored", "reason": "not incoming"}

    # Extraer datos del mensaje
    conversation_id = payload.get("conversation", {}).get("id")
    message_content = payload.get("content", "").strip()
    contact_name    = payload.get("contact", {}).get("name", "Cliente")
    contact_phone   = payload.get("contact", {}).get("phone_number", "")
    channel         = payload.get("inbox", {}).get("channel", "")

    if not conversation_id or not message_content:
        return {"status": "ignored", "reason": "missing conversation_id or content"}

    logger.info(
        f"Mensaje entrante | conv={conversation_id} | "
        f"canal={channel} | de={contact_name} ({contact_phone}) | "
        f"texto='{message_content[:80]}'"
    )

    # ─── Lógica de IA ────────────────────────────────────────────────────────
    # Aquí decides qué responder. Por ahora: respuesta automática simple.
    # En el futuro: llamar a LangGraph, OpenAI, etc.
    ai_response = await generate_ai_response(
        message=message_content,
        contact_name=contact_name,
        conversation_id=conversation_id,
    )

    if ai_response:
        success = await chatwoot_service.send_message(conversation_id, ai_response)
        if success:
            logger.info(f"Respuesta enviada a conv={conversation_id}")
        else:
            logger.error(f"Error al enviar respuesta a conv={conversation_id}")

    return {"status": "ok"}


async def generate_ai_response(message: str, contact_name: str, conversation_id: int) -> str:
    """
    Lógica de respuesta automática.
    Por ahora usa respuestas simples basadas en palabras clave.
    
    TODO: Reemplazar con llamada a LangGraph / OpenAI cuando esté listo.
    """
    message_lower = message.lower()

    # Saludo
    if any(w in message_lower for w in ["hola", "buenos", "buenas", "buen día"]):
        return (
            f"¡Hola {contact_name}! 👋 Soy el asistente virtual de *Serviglobal IA*.\n\n"
            f"Puedo ayudarte con:\n"
            f"• 📅 *Agendar una preconsultoría*\n"
            f"• ℹ️ *Información sobre nuestros servicios*\n"
            f"• 🤖 *Demo de agentes de voz con IA*\n\n"
            f"¿Con qué te puedo ayudar hoy?"
        )

    # Agendar / cita
    if any(w in message_lower for w in ["agendar", "cita", "consultoría", "reunión", "llamada"]):
        return (
            f"¡Excelente! Puedo ayudarte a agendar una *preconsultoría gratuita* (15-30 min) 📅\n\n"
            f"Por favor comparte tu disponibilidad o accede a nuestro calendario:\n"
            f"👉 https://cal.com/serviglobal\n\n"
            f"También puedes decirme qué día y hora prefieres."
        )

    # Precio / costo
    if any(w in message_lower for w in ["precio", "costo", "cuánto", "cuanto", "tarifa", "pago"]):
        return (
            f"El costo depende del alcance e integraciones requeridas para tu caso. 💡\n\n"
            f"En la *preconsultoría gratuita* analizamos tu operación y te presentamos "
            f"un plan de implementación personalizado.\n\n"
            f"¿Te gustaría agendar una sesión de diagnóstico?"
        )

    # WhatsApp / integración
    if any(w in message_lower for w in ["whatsapp", "integración", "crm", "sistema"]):
        return (
            f"Sí, integramos con WhatsApp Business, CRM, calendarios, email y telefonía VoIP. 🔌\n\n"
            f"La idea es *conectar lo que ya usas*, sin reemplazar tu infraestructura actual.\n\n"
            f"¿Quieres saber más o prefieres agendar una demo?"
        )

    # Respuesta genérica
    return (
        f"Gracias por tu mensaje, {contact_name}. 🤝\n\n"
        f"Un especialista de *Serviglobal IA* te atenderá pronto.\n\n"
        f"Si prefieres atención inmediata, puedes agendar una preconsultoría:\n"
        f"👉 https://cal.com/serviglobal"
    )
