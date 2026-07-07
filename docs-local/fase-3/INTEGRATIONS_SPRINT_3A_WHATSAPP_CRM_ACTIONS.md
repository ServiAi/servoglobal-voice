# Sprint 3A - WhatsApp CRM Actions

## Alcance implementado

- Configuracion WhatsApp Cloud API por tenant con `access_token` cifrado.
- Plantillas transaccionales por tenant en `tenant_whatsapp_templates`.
- Envio real desde CRM Lead Detail por `POST /api/v1/crm/leads/{lead_id}/actions/whatsapp`.
- Persistencia de mensajes en `crm_whatsapp_messages`.
- Actividades CRM para envio, fallo, estados e inbound asociado.
- Eventos operativos en `tenant_integration_events`.
- Webhook Meta compatible con verificacion global `WHATSAPP_VERIFY_TOKEN`.

## Endpoints

- `GET /api/v1/integrations/whatsapp/config`
- `POST /api/v1/integrations/whatsapp/config`
- `POST /api/v1/integrations/whatsapp/test`
- `GET /api/v1/integrations/whatsapp/templates`
- `POST /api/v1/crm/leads/{lead_id}/actions/whatsapp`
- `GET /api/v1/crm/leads/{lead_id}/messages`
- `GET /api/v1/webhook/whatsapp`
- `POST /api/v1/webhook/whatsapp`
- `GET/POST /api/v1/admin/tenants/{tenant_id}/integrations/whatsapp/config`
- `POST /api/v1/admin/tenants/{tenant_id}/integrations/whatsapp/test`
- `GET /api/v1/admin/tenants/{tenant_id}/integrations/whatsapp/templates`

## Seguridad

- El frontend nunca envia `tenant_id`; se toma del contexto autenticado o de rutas admin internas.
- El token Meta no se devuelve al frontend y se guarda cifrado.
- Los logs de webhooks registran solo contadores.
- No se persisten payloads completos de Meta.
- Inbound solo se asocia si existe contacto y lead abierto del tenant; no crea leads inseguros.

## Archivos principales

- `backend/alembic/versions/202607030001_integrations_3a_whatsapp_crm_actions.py`
- `backend/app/services/whatsapp_client.py`
- `backend/app/services/whatsapp_config_service.py`
- `backend/app/services/whatsapp_message_service.py`
- `backend/app/services/whatsapp_template_service.py`
- `frontend/components/crm/CrmSendWhatsAppModal.tsx`
- `frontend/components/crm/integrations/WhatsAppIntegrationCard.tsx`
