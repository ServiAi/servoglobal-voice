# Arquitectura

## Componentes

### Frontend

Next.js 15 con App Router, React 18, TypeScript, Tailwind y `next-intl`. Se divide en landing pública, dashboard tenant, CRM, configuración de integraciones, automatizaciones/notificaciones y administración de plataforma. Las llamadas privadas pasan por utilidades de autenticación Auth0 y clientes tipados en `frontend/lib/api/`.

La UI de notificaciones se compone de `NotificationsWorkspace`, `RulesPanel`, `RecipientsPanel` y `DeliveriesPanel`. Las mutaciones se ejecutan mediante Server Actions para que el bearer token no viaje al cliente. `FieldHelp` es el componente compartido para ayudas contextuales de formularios; usa `<details>`, mantiene interacción por teclado y cierra con un clic externo.

Voice Experiences usa Server Components para resolver autenticación, permisos y datos iniciales. Sus clientes tipados son `server-only` y las mutaciones pasan por Server Actions; ningún bearer token llega a componentes cliente. El builder comparte un formulario controlado entre wizard y editor, administra schemas versionados y genera una vista previa React local que no usa micrófono, WebRTC ni endpoints de ejecución.

El tema visual (`logo_url`, `primary_color`, `background_color`, `color_scheme`) vive dentro de `theme_json`, se versiona junto con el resto del contenido en cada publicación y se resuelve con la misma función (`resolveVoiceTheme`) tanto en la vista previa del editor como en el formulario público, para que ambos rendericen de forma idéntica. `color_scheme` es `light` por defecto para preservar las experiencias publicadas antes de esta funcionalidad.

Cada experiencia publicada expone además `/{locale}/voice/{slug}/embed`: la misma página pública (mismo submission, Turnstile, `context_token` y WebRTC) sin cabecera de sitio ni márgenes de página completa, pensada para incrustarse en un `<iframe>`. Un `ResizeObserver` dentro del formulario notifica su altura al documento padre vía `postMessage` (`voice-embed:resize`). El middleware de Next.js agrega `Content-Security-Policy: frame-ancestors *` únicamente a esa ruta `/embed`; el resto del sitio no declara política de framing. El SDK vanilla `frontend/public/voice-embed.v1.js` (sin build propio) monta el iframe como inline, botón flotante o modal disparado por un selector CSS del sitio anfitrión, y expone `window.VoiceEmbed` para uso imperativo desde React. El panel "Compartir / Incrustar" del listado de experiencias genera el enlace público (usando `experience.default_locale`, no el idioma del administrador) y los fragmentos de código (HTML/React/iframe) para cada modo.

### Backend

FastAPI organiza routers en `backend/app/api/endpoints/`, reglas de negocio en `backend/app/services/`, contratos en `schemas/` y persistencia SQLAlchemy en `models/`. `backend/app/main.py` ensambla middleware, CORS y routers.

El subsistema de notificaciones separa administración (`notification_admin_service.py`), creación segura de eventos (`notification_event_pipeline.py`), planificación (`notification_orchestrator.py`), condiciones/destinatarios/variables, claims, reintentos, recuperación y ejecución WhatsApp. `backend/app/workers/notification_worker.py` procesa entregas vencidas fuera del proceso web y requiere PostgreSQL.

### Datos

PostgreSQL es la base principal. Alembic administra el esquema. Los dominios persistentes son identidad/tenant, llamadas/analítica, CRM, billing/uso, integraciones y notificaciones. Notificaciones usa `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events` y `notification_deliveries`. Los binarios de email se almacenan mediante `StorageService` en disco local o S3 compatible; la DB guarda metadata. Chatwoot es multi-tenant vía `tenant_chatwoot_configs` (una Account por tenant, `mode` external/managed, token cifrado, `webhook_key` único, `platform_agent_bot_id` cuando el modo es managed) y `tenant_chatwoot_inboxes` (inboxes adicionales opcionales); no hay tabla ni configuración global de credenciales por tenant. La excepción es `CHATWOOT_PLATFORM_API_TOKEN`: un token de Super Admin de la instancia compartida, global y fuera de `tenant_chatwoot_configs`, usado sólo por `ChatwootPlatformClient` para aprovisionar Accounts nuevas en modo managed.

## Límites de confianza

- Auth0 autentica la aplicación privada; el backend resuelve usuario, membresía, rol y tenant.
- Las rutas tenant derivan `tenant_id` del contexto autenticado.
- Las rutas `/api/v1/admin/...` requieren autorización de plataforma y pueden seleccionar tenant explícitamente.
- La familia `/api/v1/admin/notifications` es una excepción nominal: también admite roles tenant. Toda operación sobre recursos deriva el tenant de `AuthContext`; el catálogo común sigue autenticado y ningún endpoint acepta `tenant_id` del body o query.
- Webhooks verifican firma o secreto cuando el proveedor lo soporta. Chatwoot no firma sus webhooks salientes: el aislamiento por tenant usa un `webhook_key` opaco en la URL (`POST /api/v1/webhooks/chatwoot/{webhook_key}`) más un cross-check de `payload.account.id` contra la Account configurada.
- Herramientas internas de voz usan secreto compartido y nunca aceptan un tenant arbitrario sin resolver contexto seguro.
- Los secretos por tenant se cifran; las respuestas sólo indican presencia mediante campos como `has_secret`.

## Flujos principales

### Llamada a CRM

1. La landing o el CRM solicita/inicia una llamada.
2. Cada ruta tenant usa el mismo identificador `route-<uuid>` como usuario SIP y nombre de endpoint PJSIP; el backend lo deriva y la UI no permite sustituirlo.
3. Ultravox ejecuta la llamada y envía eventos.
4. El backend normaliza y persiste la llamada de forma idempotente; el worker consulta el estado del proveedor como respaldo cuando falta el evento terminal.
5. Los servicios CRM resuelven contacto/lead, contexto y etapa.
6. `VoiceCapacityService` centraliza los estados que ocupan un canal SIP, registra saturaciones y cierres de respaldo en `tenant_integration_events`, y calcula la capacidad actual aislada por tenant.
7. El dashboard separa el rendimiento reportado por Ultravox de la capacidad SIP actual; sus contadores de capacidad respetan el período, mientras ocupación y cupos son una fotografía en vivo.
8. El dashboard y timeline consultan la información ya persistida.

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

`TenantWhatsAppTemplate` modela un ciclo de vida propio (`draft → pending → approved | rejected`, más `disabled`) separado del estado crudo de Meta (`meta_status`). Una plantilla llega a `status="approved"` por dos caminos: sincronización masiva de plantillas ya aprobadas en Meta Business Manager (`source="meta_sync"`, variables `POSITIONAL` `{{1}}`), o creación local (`source="tenant_authored"`, variables `NAMED` `{{nombre}}`) seguida de envío a Meta (`WhatsAppConfigService.submit_template`) y sincronización manual de estado (`sync_template_status`). `WhatsAppTemplateService.get_synced_template()` es el único punto de verdad para "¿esta plantilla se puede enviar?": exige `status=="approved"`, sin importar el origen.

Flow Studio V1 permanece dentro de la misma integración y reutiliza `TenantWhatsAppConfig`, el token cifrado y el WABA ID. `TenantWhatsAppFlow` guarda una fila por versión; `published` y `deprecated` son inmutables. El frontend edita únicamente `builder_json` versión 1. `WhatsAppFlowCompiler` lo valida y produce Flow JSON 7.3 canonicalizado con hash SHA-256; `WhatsAppFlowService` aplica ownership tenant, snapshots de Context Schema, versionado, persistencia y eventos; `WhatsAppCloudClient` concentra create, metadata, multipart asset upload, status, publish, deprecate y delete. El navegador nunca llama a Graph API.

La generación desde Context Schema incluye `ask_if_missing` y `prefill_and_confirm`, preserva el binding en el builder y excluye `trust_prefill`, `internal_only` y `collect_during_call` porque V1 es estático. El snapshot evita que cambios futuros del schema alteren una versión existente. No existe todavía ingestión de respuestas, Data Exchange, endpoint encryption ni runtime de voz desde WhatsApp.

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

- Una regla WhatsApp ejecutable necesita una plantilla con `status="approved"` (importada por sync desde Meta o creada en la app, enviada y aprobada), además de todos sus parámetros obligatorios mapeados.
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
