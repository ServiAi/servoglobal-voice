import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class WhatsAppService:
    def __init__(self):
        self.api_token = settings.WHATSAPP_API_TOKEN
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.base_url = f"https://graph.facebook.com/v23.0/{self.phone_number_id}/messages"

    async def send_template_message(self, to: str, template_name: str, language_code: str = "es-CO", components: list = None):
        """
        Envía un mensaje usando una plantilla pre-aprobada de WhatsApp.
        """
        if not self.api_token or not self.phone_number_id:
            logger.error("Faltan variables de entorno de WhatsApp.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        to_clean = to.replace("+", "").replace(" ", "").strip() 

        payload = {
            "messaging_product": "whatsapp",
            "to": to_clean,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }

        if components:
            payload["template"]["components"] = components

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                logger.info(f"Mensaje de WhatsApp enviado correctamente a {to}.")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Error HTTP al enviar WhatsApp: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"Error inesperado al enviar WhatsApp: {str(e)}")
                return None

whatsapp_service = WhatsAppService()
