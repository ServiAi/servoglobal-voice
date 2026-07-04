# Sprint 3 - Reglas globales para agentes IA

## Objetivo del Sprint 3

Construir dos integraciones en paralelo:

1. WhatsApp CRM Actions reales.
2. Voice CRM Actions reales.

Cada integracion debe ser:

- Multitenant.
- Segura.
- Trazable.
- Compatible con el CRM existente.
- Compatible con las integraciones ya implementadas.

## Estado actual del sistema

El sistema ya cuenta con:

- Email transaccional con Resend.
- Email Composer.
- Adjuntos con MinIO/S3.
- Formularios publicos.
- Resumen de llamada.
- Cal.com booking engine.
- Cancelacion y reprogramacion Cal.com.
- Reconciliacion por webhook Cal.com.
- Google Calendar foundation.
- Voice booking tools protegidos.
- CRM timeline.
- Tenant integration events.

Ningun agente debe romper estas funcionalidades.

## Principios de arquitectura

- El CRM es la fuente de verdad.
- Cada integracion debe ser multitenant.
- Cada integracion debe tener trazabilidad en timeline.
- Cada integracion debe registrar eventos en `tenant_integration_events`.
- Los secretos deben cifrarse usando `SecretManagerService`.
- La UI tenant no debe enviar `tenant_id`.
- Los endpoints admin pueden recibir `tenant_id`, pero deben validar acceso interno.
- Los endpoints internos deben tener proteccion propia.
- Los webhooks deben validar firma o secreto cuando aplique.
- No guardar payloads completos de proveedores.
- No exponer secretos al frontend.
- No duplicar logica existente.
- No modificar modulos de otra integracion sin autorizacion explicita.

## Separacion de responsabilidades

WhatsApp y Voz deben implementarse en ramas separadas.

Codex debe trabajar unicamente en la integracion WhatsApp.

Antigravity debe trabajar unicamente en la integracion Voz.

WhatsApp no debe modificar servicios de Voz.

Voz no debe modificar servicios de WhatsApp.

Si ambos necesitan modificar un archivo compartido, deben hacerlo de forma minima, documentada y con tests de regresion.

## Archivos compartidos de alto riesgo

Los siguientes archivos deben modificarse con especial cuidado:

- `backend/app/main.py`
- `backend/app/api/endpoints/crm.py`
- `backend/app/api/endpoints/integrations.py`
- `backend/app/api/endpoints/admin/tenants.py`
- `backend/app/models/crm.py`
- `backend/app/models/integrations.py`
- `backend/app/schemas/crm.py`
- `backend/app/schemas/integrations.py`
- `frontend/lib/api/crm.ts`
- `frontend/types/crm.ts`
- `frontend/components/crm/CrmLeadQuickActions.tsx`
- `frontend/app/[locale]/crm/settings/integrations/page.tsx`
- `frontend/app/[locale]/admin/tenants/[tenantId]/integrations/page.tsx`

Preferir subrouters, servicios y componentes aislados antes que agrandar archivos existentes.
