# Sprint Integraciones 1A Resend transaccional

## Objetivo

Implementar Resend transaccional por tenant y envio de propuesta/resumen desde CRM Lead Detail.

## Alcance

- Base minima de integraciones por tenant.
- SecretManager para cifrar API keys.
- Configuracion Resend por tenant.
- Email de prueba.
- Templates internos minimos.
- Envio desde CRM Lead Detail.
- Registro de TenantEmailSend.
- Registro de CrmActivity en timeline.
- Modelo y validacion base para adjuntos controlados.
- UI minima para configurar Resend y enviar email desde un lead.

## MCPs usados

- GitHub MCP: validar repo, default branch y rama `develop`.
- CodeGraph MCP: mapear modelos CRM/identity, endpoint CRM email stub, servicios CRM y flujo Lead Detail.
- Context7 MCP: no usable en esta sesion por API key invalida; se uso documentacion oficial publica como fallback.
- Postgres MCP: no se uso contra produccion. La validacion de migracion se deja contra base configurada local/staging autorizada.
- ponytail-repo MCP: no disponible como MCP en esta sesion; no se modifico `ponytail-repo/`.

## Modelos creados

- `TenantIntegration`
- `TenantIntegrationEvent`
- `TenantEmailConfig`
- `TenantEmailTemplate`
- `TenantEmailAsset`
- `TenantEmailSend`

## Migracion

- `backend/alembic/versions/202606270001_integrations_1a_resend.py`

## Endpoints

- `GET /api/v1/integrations`
- `POST /api/v1/integrations/resend/config`
- `POST /api/v1/integrations/resend/test`
- `GET /api/v1/integrations/resend/templates`
- `POST /api/v1/integrations/resend/templates`
- `POST /api/v1/crm/leads/{lead_id}/actions/email`

## Servicios

- `SecretManager`
- `IntegrationService`
- `IntegrationEventService`
- `EmailConfigService`
- `EmailTemplateService`
- `EmailAssetService`
- `EmailSendService`
- `ResendService`
- `StorageService`

## Flujo configuracion Resend

Tenant admin o platform admin guarda sender, reply-to, dominio y API key. La API key se cifra antes de persistirse y nunca vuelve al frontend. Si el usuario edita sin enviar API key, se conserva el secreto existente.

## Flujo email desde lead

El modal de Lead Detail selecciona template, subject y message. El backend resuelve el lead por `context.tenant.id`, valida contacto con email, Resend activo, template activo y assets del tenant. Preview renderiza sin crear send ni llamar Resend. Envio real crea `TenantEmailSend pending`, llama Resend con `Idempotency-Key`, marca `sent` o `failed`, registra activity y evento de integracion.

## Seguridad

- No se acepta `tenant_id` desde frontend.
- API key cifrada con `INTEGRATIONS_ENCRYPTION_KEY`.
- Fallback de secreto solo para tests.
- Respuestas de configuracion solo devuelven `has_secret`.
- Logs de Resend no incluyen API key, payload completo, HTML, texto, adjuntos ni email completo.
- Metadata de eventos se sanitiza.

## Adjuntos

Se agregaron modelo, storage local y validacion de asset IDs existentes por tenant. No se expuso UI ni endpoints de upload en esta primera parte.

## Fuera de alcance

- Cal.com booking.
- Google Calendar.
- Marketing masivo.
- Resend Broadcasts.
- Webhooks Resend.
- Editor visual complejo.
- Automatizaciones.
- IA para redactar propuestas.

## Tests nuevos

- `backend/test_integrations_base.py`
- `backend/test_resend_integration.py`
- `backend/test_crm_email_action.py`

## Riesgos pendientes

- Confirmar `INTEGRATIONS_ENCRYPTION_KEY` en staging antes de deploy.
- Ejecutar migracion contra local/staging autorizado, nunca produccion.
- Definir UX/upload de assets en un sprint posterior si se quieren adjuntos desde UI.
