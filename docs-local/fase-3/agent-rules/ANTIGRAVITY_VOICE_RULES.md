# Reglas para Antigravity - Sprint 3B Voz

## Rama obligatoria

Trabajar unicamente en:

```text
feature/sprint-3b-voice-integration-antigravity
```

## Objetivo

Implementar Voice CRM Actions reales, multitenant y trazables.

## Funcionalidades a construir

* Configuracion proveedor de voz por tenant.
* Configuracion de agentes de voz.
* Accion real "Llamar" desde Lead Detail.
* Creacion de llamada saliente.
* Registro de llamada en CRM.
* Timeline CRM.
* `tenant_integration_events`.
* Webhook de eventos de llamada.
* Asociacion llamada-lead-contact.
* Seguridad para endpoints internos.
* UI de configuracion de voz.
* UI de accion de llamada desde Lead Detail.

## Archivos permitidos

Preferir crear archivos propios:

```text
backend/app/services/voice_client.py
backend/app/services/voice_config_service.py
backend/app/services/voice_call_service.py
backend/app/services/voice_agent_service.py
backend/app/api/endpoints/crm_voice.py
backend/app/api/endpoints/voice_webhook.py

frontend/components/crm/integrations/VoiceIntegrationCard.tsx
frontend/components/crm/integrations/VoiceConfigForm.tsx
frontend/components/crm/actions/VoiceQuickAction.tsx
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
backend/app/api/endpoints/voice.py
backend/app/api/endpoints/ultravox_webhook.py

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
backend/app/services/whatsapp_client.py
backend/app/services/whatsapp_config_service.py
backend/app/services/whatsapp_message_service.py
backend/app/api/endpoints/whatsapp_webhook.py
frontend/components/crm/CrmSendWhatsAppModal.tsx
backend/app/services/booking_service.py
backend/app/services/calcom_client.py
backend/app/api/endpoints/calcom.py
```

## Reglas de seguridad Voz

* No loguear API keys de proveedor de voz.
* No loguear payload completo de llamadas.
* No loguear telefono completo.
* No loguear grabaciones completas ni URLs sensibles si contienen tokens.
* Los endpoints internos deben estar protegidos por secreto, firma o JWT interno.
* No aceptar `tenant_id` arbitrario desde herramientas internas.
* Resolver tenant desde contexto confiable: `call_context_id`, agente, DID o configuracion interna.
* Asociar llamadas a lead/contact solo si la relacion es segura.

## Tests minimos

Crear o actualizar:

```text
backend/test_voice_integration.py
backend/test_crm_voice_action.py
backend/test_voice_webhook.py
```

Ejecutar:

```bash
cd backend

python -m unittest test_voice_integration.py
python -m unittest test_crm_voice_action.py
python -m unittest test_voice_webhook.py
python -m unittest test_voice_booking_tools.py

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
* Seguridad de endpoints internos.
* Timeline CRM.
* Integration events.
* Tests ejecutados.
* Frontend build.
* Riesgos pendientes.
