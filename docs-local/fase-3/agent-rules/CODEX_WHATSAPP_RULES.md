# Reglas para Codex - Sprint 3A WhatsApp

## Rama obligatoria

Trabajar unicamente en:

```text
feature/sprint-3a-whatsapp-crm-actions-codex
```

## Objetivo

Implementar WhatsApp CRM Actions reales, multitenant y trazables.

## Funcionalidades a construir

* Configuracion WhatsApp por tenant.
* Access token cifrado.
* WhatsApp Cloud Client.
* Envio real desde Lead Detail.
* Modal de envio WhatsApp.
* Plantillas transaccionales basicas.
* Registro de mensajes.
* Timeline CRM.
* `tenant_integration_events`.
* Webhook de estados `sent`, `delivered`, `read`, `failed`.
* Asociacion basica de mensajes entrantes a lead/contact.
* UI de configuracion WhatsApp.
* Endpoints admin para configuracion WhatsApp.

## Archivos permitidos

Preferir crear archivos propios:

```text
backend/app/services/whatsapp_client.py
backend/app/services/whatsapp_config_service.py
backend/app/services/whatsapp_message_service.py
backend/app/services/whatsapp_template_service.py
backend/app/api/endpoints/crm_whatsapp.py
backend/app/api/endpoints/whatsapp_webhook.py

frontend/components/crm/integrations/WhatsAppIntegrationCard.tsx
frontend/components/crm/integrations/WhatsAppConfigForm.tsx
frontend/components/crm/CrmSendWhatsAppModal.tsx
frontend/components/crm/messages/LeadMessagesList.tsx
```

## Archivos compartidos que se pueden modificar con cuidado

```text
backend/app/main.py
backend/app/models/crm.py
backend/app/models/integrations.py
backend/app/schemas/crm.py
backend/app/schemas/integrations.py
backend/app/api/endpoints/integrations.py
backend/app/api/endpoints/admin/tenants.py

frontend/lib/api/crm.ts
frontend/types/crm.ts
frontend/components/crm/CrmLeadQuickActions.tsx
frontend/app/[locale]/crm/settings/integrations/page.tsx
frontend/app/[locale]/admin/tenants/[tenantId]/integrations/page.tsx
```

## Archivos prohibidos

No tocar:

```text
.env
opencode.jsonc
backend/app/services/booking_service.py
backend/app/services/calcom_client.py
backend/app/api/endpoints/calcom.py
backend/app/api/endpoints/voice_booking_tools.py
backend/app/services/voice_booking_context_service.py
frontend/components/crm/bookings/LeadBookingModal.tsx
```

## Reglas de seguridad WhatsApp

* El token de WhatsApp Cloud API debe cifrarse.
* No devolver token al frontend.
* No loguear token.
* No loguear payload completo de Meta.
* No loguear telefono completo.
* No loguear contenido completo del mensaje.
* Webhook debe validar `verify_token`.
* Status webhook debe asociarse por `provider_message_id`.
* Si no se puede asociar un mensaje entrante de forma segura, registrar evento seguro sin crear lead automaticamente.

## Tests minimos

Crear o actualizar:

```text
backend/test_whatsapp_integration.py
backend/test_crm_whatsapp_action.py
backend/test_whatsapp_webhook.py
```

Ejecutar:

```bash
cd backend

python -m unittest test_whatsapp_integration.py
python -m unittest test_crm_whatsapp_action.py
python -m unittest test_whatsapp_webhook.py

python -m unittest test_calcom_integration.py
python -m unittest test_calcom_cancel_reschedule.py
python -m unittest test_crm_bookings.py
python -m unittest test_resend_integration.py
python -m unittest test_crm_email_action.py

python -m compileall app

cd ../frontend

npm.cmd run lint
npx.cmd tsc --noEmit
npm.cmd run build

cd ..
git diff --check
```

## Reporte final

Reportar:

* Archivos modificados.
* Modelos creados.
* Endpoints creados.
* Servicios creados.
* Seguridad de secretos.
* Timeline CRM.
* Integration events.
* Tests ejecutados.
* Frontend build.
* Riesgos pendientes.
