# Arquitectura

## Componentes

### Frontend

Next.js 15 con App Router, React 18, TypeScript, Tailwind y `next-intl`. Se divide en landing pública, dashboard tenant, CRM, configuración de integraciones y administración de plataforma. Las llamadas privadas pasan por utilidades de autenticación Auth0 y clientes tipados en `frontend/lib/api/`.

### Backend

FastAPI organiza routers en `backend/app/api/endpoints/`, reglas de negocio en `backend/app/services/`, contratos en `schemas/` y persistencia SQLAlchemy en `models/`. `backend/app/main.py` ensambla middleware, CORS y routers.

### Datos

PostgreSQL es la base principal. Alembic administra el esquema. Los dominios persistentes son identidad/tenant, llamadas/analítica, CRM, billing/uso e integraciones. Los binarios de email se almacenan mediante `StorageService` en disco local o S3 compatible; la DB guarda metadata.

## Límites de confianza

- Auth0 autentica la aplicación privada; el backend resuelve usuario, membresía, rol y tenant.
- Las rutas tenant derivan `tenant_id` del contexto autenticado.
- Las rutas `/api/v1/admin/...` requieren autorización de plataforma y pueden seleccionar tenant explícitamente.
- Webhooks verifican firma o secreto cuando el proveedor lo soporta.
- Herramientas internas de voz usan secreto compartido y nunca aceptan un tenant arbitrario sin resolver contexto seguro.
- Los secretos por tenant se cifran; las respuestas sólo indican presencia mediante campos como `has_secret`.

## Flujos principales

### Llamada a CRM

1. La landing o el CRM solicita/inicia una llamada.
2. Ultravox ejecuta la llamada y envía eventos.
3. El backend normaliza y persiste la llamada de forma idempotente.
4. Los servicios CRM resuelven contacto/lead, contexto y etapa.
5. El dashboard y timeline consultan la información ya persistida.

### Email

1. El usuario compone o previsualiza contenido seguro.
2. Backend valida lead, email, template, tokens y assets dentro del tenant.
3. Resend recibe el mensaje con idempotency key.
4. Se actualiza `TenantEmailSend` y se registran actividad y evento de integración.

### Reserva

1. CRM o herramienta de voz consulta slots con configuración tenant.
2. `BookingService` crea primero la reserva CRM en estado pendiente.
3. `CalComClient` opera con Cal.com y devuelve identificadores seguros.
4. CRM, timeline y eventos se actualizan; el webhook reconcilia cambios posteriores.

### WhatsApp y voz

Cada canal conserva configuración, cliente, servicio de negocio, persistencia, endpoints y pruebas propios. Comparten identidad tenant, timeline CRM y eventos de integración, sin compartir secretos ni payloads completos.

## Principios de cambio

- CRM es la fuente de verdad comercial.
- La integración externa no debe saltarse servicios de dominio.
- Mantener cambios mínimos en routers/modelos compartidos.
- Registrar metadata segura, no payloads completos.
- Preservar idempotencia y aislamiento tenant en reintentos y webhooks.
