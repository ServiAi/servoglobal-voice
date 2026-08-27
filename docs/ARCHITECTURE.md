# Arquitectura

## Componentes

### Frontend

Next.js 15 con App Router, React 18, TypeScript, Tailwind y `next-intl`. Se divide en landing pública, dashboard tenant, CRM, configuración de integraciones, automatizaciones/notificaciones y administración de plataforma. Las llamadas privadas pasan por utilidades de autenticación Auth0 y clientes tipados en `frontend/lib/api/`.

La UI de notificaciones se compone de `NotificationsWorkspace`, `RulesPanel`, `RecipientsPanel` y `DeliveriesPanel`. Las mutaciones se ejecutan mediante Server Actions para que el bearer token no viaje al cliente. `FieldHelp` es el componente compartido para ayudas contextuales de formularios; usa `<details>`, mantiene interacción por teclado y cierra con un clic externo.

Voice Experiences usa Server Components para resolver autenticación, permisos y datos iniciales. Sus clientes tipados son `server-only` y las mutaciones pasan por Server Actions; ningún bearer token llega a componentes cliente. El builder comparte un formulario controlado entre wizard y editor, administra schemas versionados y genera una vista previa React local que no usa micrófono, WebRTC ni endpoints de ejecución.

### Backend

FastAPI organiza routers en `backend/app/api/endpoints/`, reglas de negocio en `backend/app/services/`, contratos en `schemas/` y persistencia SQLAlchemy en `models/`. `backend/app/main.py` ensambla middleware, CORS y routers.

El subsistema de notificaciones separa administración (`notification_admin_service.py`), creación segura de eventos (`notification_event_pipeline.py`), planificación (`notification_orchestrator.py`), condiciones/destinatarios/variables, claims, reintentos, recuperación y ejecución WhatsApp. `backend/app/workers/notification_worker.py` procesa entregas vencidas fuera del proceso web y requiere PostgreSQL.

### Datos

PostgreSQL es la base principal. Alembic administra el esquema. Los dominios persistentes son identidad/tenant, llamadas/analítica, CRM, billing/uso, integraciones y notificaciones. Notificaciones usa `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events` y `notification_deliveries`. Los binarios de email se almacenan mediante `StorageService` en disco local o S3 compatible; la DB guarda metadata.

## Límites de confianza

- Auth0 autentica la aplicación privada; el backend resuelve usuario, membresía, rol y tenant.
- Las rutas tenant derivan `tenant_id` del contexto autenticado.
- Las rutas `/api/v1/admin/...` requieren autorización de plataforma y pueden seleccionar tenant explícitamente.
- La familia `/api/v1/admin/notifications` es una excepción nominal: también admite roles tenant. Toda operación sobre recursos deriva el tenant de `AuthContext`; el catálogo común sigue autenticado y ningún endpoint acepta `tenant_id` del body o query.
- Webhooks verifican firma o secreto cuando el proveedor lo soporta.
- Herramientas internas de voz usan secreto compartido y nunca aceptan un tenant arbitrario sin resolver contexto seguro.
- Los secretos por tenant se cifran; las respuestas sólo indican presencia mediante campos como `has_secret`.

## Flujos principales

### Llamada a CRM

1. La landing o el CRM solicita/inicia una llamada.
2. Ultravox ejecuta la llamada y envía eventos.
3. El backend normaliza y persiste la llamada de forma idempotente; el worker consulta el estado del proveedor como respaldo cuando falta el evento terminal.
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

### Automatizaciones y notificaciones

1. Un cambio de reserva o llamada entra a `NotificationEventPipeline`, que crea o reutiliza un `DomainEvent` con identidad idempotente y payload seguro.
2. `NotificationOrchestrator` selecciona capacidades y reglas activas, evalúa condiciones, resuelve destinatarios y calcula `scheduled_for`.
3. Se crea o reconcilia una `NotificationDelivery` mediante una clave idempotente por evento, regla, canal y destinatario.
4. El worker reclama lotes vencidos con lease. `WhatsAppNotificationExecutor` vuelve a comprobar cancelaciones, ownership del claim y vigencia del evento antes de enviar.
5. El resultado actualiza entrega y mensaje CRM. Los errores transitorios siguen la política de reintentos; entregas antiguas o inconsistentes pasan por recuperación, `manual_review` o estado terminal.
6. La UI tenant consulta resumen, reglas, destinatarios y entregas con destinos enmascarados; nunca recibe claim tokens, payloads internos ni secretos.
7. `notification_event_schemas.py` es la fuente única de metadata para UI, validación administrativa y runtime: relaciona capacidad/evento con versión, campos tipados, operadores, formatos, rutas de destinatario y un ejemplo sintético seguro.

El evaluador admite composición `all`/`any` y rutas seguras sobre diccionarios; no usa `eval`. El endpoint de dry-run reutiliza el validador, evaluador, mapper y resolver de destinatarios de producción, pero no publica eventos, no crea entregas y no invoca WhatsApp. Las mutaciones y pruebas de reglas generan auditoría técnica sin payloads, variables, previews ni destinatarios.

### Invariantes de la UI de notificaciones

- Una regla WhatsApp ejecutable necesita una plantilla Meta sincronizada, activa y `APPROVED`, además de todos sus parámetros obligatorios mapeados.
- Campos y operadores se seleccionan desde el contrato del evento. Números, booleanos, enums y fechas usan controles tipados; los operadores de existencia no conservan un valor residual.
- Cambiar la capacidad limpia el evento dependiente. Las reglas antiguas con rutas fuera del contrato quedan visibles como configuración obsoleta y no se guardan hasta corregirlas.
- Las variables de plantilla se generan desde los parámetros Meta y las rutas del evento; el preview y la prueba muestran sólo datos sintéticos o introducidos por el administrador y destinatarios enmascarados.
- Los diálogos largos usan encabezado fijo en su fila, cuerpo con `overflow-y-auto` y `DialogFooter` en una fila separada.
- Cada campo del formulario de reglas conserva una ayuda contextual traducida. El contenido se abre desde el ícono y se oculta con cualquier clic externo.
- Destinos y destinatarios se muestran enmascarados. Los cambios no deben introducir `tenant_id` en payloads del frontend.

## Principios de cambio

- CRM es la fuente de verdad comercial.
- La integración externa no debe saltarse servicios de dominio.
- Mantener cambios mínimos en routers/modelos compartidos.
- Registrar metadata segura, no payloads completos.
- Preservar idempotencia y aislamiento tenant en reintentos y webhooks.
