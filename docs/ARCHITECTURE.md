# Arquitectura

## Componentes

### Frontend

Next.js 15 con App Router, React 18, TypeScript, Tailwind y `next-intl`. Se divide en landing pública y aplicación privada de tenant. Las llamadas privadas pasan por utilidades de autenticación Auth0 y clientes tipados en `frontend/lib/api/`.

La aplicación privada de tenant vive bajo el route group `frontend/app/[locale]/(tenant)/` (no agrega segmento a la URL) y comparte una única capa de autenticación y `TenantShell` (`frontend/components/tenant/shell/`: `TenantShell`, `TenantSidebar`, `TenantTopbar`, `TenantNavigation`, `TenantMobileDrawer`) entre todos sus dominios, en vez de un shell acoplado al CRM. La navegación agrupa por dominio de producto, no por CRM: Inicio (`/dashboard`, resumen ejecutivo del tenant), CRM (`/crm` resumen comercial, `/crm/leads`, `/crm/tasks`, `/crm/analytics` rendimiento comercial completo), Voz IA (`/voice-ai/experiences`, `/voice-ai/calls`, `/voice-ai/analytics`, `/voice-ai/telephony` con `VoiceCapacityPanel`), Automatización (`/automations/notifications`) e Integraciones (`/integrations`, transversal a toda la plataforma). Cada ruta legacy (`/crm/dashboard`, `/crm/settings/integrations(?:/.*)?`, `/crm/settings/notifications`, `/crm/settings/voice-experiences(?:/.*)?`, y el antiguo `/dashboard -> /crm`) conserva un stub `redirect()` a su ubicación nueva, preservando query params.

La UI de notificaciones se compone de `NotificationsWorkspace`, `RulesPanel`, `RecipientsPanel` y `DeliveriesPanel`. Las mutaciones se ejecutan mediante Server Actions para que el bearer token no viaje al cliente. `FieldHelp` es el componente compartido para ayudas contextuales de formularios; usa `<details>`, mantiene interacción por teclado y cierra con un clic externo.

Voice Experiences usa Server Components para resolver autenticación, permisos y datos iniciales. Sus clientes tipados son `server-only` y las mutaciones pasan por Server Actions; ningún bearer token llega a componentes cliente. El builder comparte un formulario controlado entre wizard y editor, administra schemas versionados y genera una vista previa React local que no usa micrófono, WebRTC ni endpoints de ejecución.

Agent Builder incorpora una prueba WebRTC detrás de `voice_runtime_v2`. Sus Server Actions crean la `VoiceSession` y solicitan el token sin exponer el bearer al cliente. `LiveKitVoiceRuntimeAdapter` es el único dueño del micrófono en este flujo, reproduce tracks remotos y libera Room, tracks, elementos de audio y listeners al finalizar. El adapter legacy Ultravox permanece separado para las experiencias públicas existentes.

El tema visual (`logo_url`, `primary_color`, `background_color`, `color_scheme`) vive dentro de `theme_json`, se versiona junto con el resto del contenido en cada publicación y se resuelve con la misma función (`resolveVoiceTheme`) tanto en la vista previa del editor como en el formulario público, para que ambos rendericen de forma idéntica. `color_scheme` es `light` por defecto para preservar las experiencias publicadas antes de esta funcionalidad.

Cada experiencia publicada expone además `/{locale}/voice/{slug}/embed`: la misma página pública (mismo submission, Turnstile, `context_token` y WebRTC) sin cabecera de sitio ni márgenes de página completa, pensada para incrustarse en un `<iframe>`. Un `ResizeObserver` dentro del formulario notifica su altura al documento padre vía `postMessage` (`voice-embed:resize`). El middleware de Next.js agrega `Content-Security-Policy: frame-ancestors *` únicamente a esa ruta `/embed`; el resto del sitio no declara política de framing. El SDK vanilla `frontend/public/voice-embed.v1.js` (sin build propio) monta el iframe como inline, botón flotante o modal disparado por un selector CSS del sitio anfitrión, y expone `window.VoiceEmbed` para uso imperativo desde React. El panel "Compartir / Incrustar" del listado de experiencias genera el enlace público (usando `experience.default_locale`, no el idioma del administrador) y los fragmentos de código (HTML/React/iframe) para cada modo.

### Backend

FastAPI organiza routers en `backend/app/api/endpoints/`, reglas de negocio en `backend/app/services/`, contratos en `schemas/` y persistencia SQLAlchemy en `models/`. `backend/app/main.py` ensambla middleware, CORS y routers.

El dominio Agent Builder (`backend/app/models/agents.py`, `agent_service.py`, `agent_compiler_service.py`, `voice_selection_service.py`, `api/endpoints/agents.py`) introduce `TenantAgent`/`TenantAgentVersion` como fuente de verdad provider-agnostic del agente, separada de `TenantVoiceAgentConfig` (config legacy ligada a Ultravox). La voz del agente es `AgentVoiceConfig` (`mode: "provider"|"provider_external"`), validada localmente por `VoiceSelectionService` (sin I/O al guardar un draft) y por `voice_registry.validate_voice_compatibility`; `AgentService.publish()` añade un preflight remoto barato (accesibilidad de la voz o BYOK del proveedor externo, nunca genera audio). Ver `docs-local/fase-4/AGENT_BUILDER_ARCHITECTURE.md` para el diseño histórico de Fase 1/Fase 2/Sprint 0 (con nota de actualización) y `docs/PROJECT_STATUS.md` para el estado actual de la abstracción de voz.

`runtime_binding_json` también versiona parámetros de modelo y tools, ambos sobre el mismo `TenantAgentVersion` sin tablas nuevas. `realtime.settings` (p.ej. `temperature`) se valida contra `voice_registry.validate_model_settings()` (puro, contra `VoiceModel.parameters: dict[str, ParameterSpec]`, sin I/O). `tools` (top-level, sibling de `realtime`) es una lista de `{key, enabled, config}` validada contra `app.domain.tool_registry` (mismo patrón que `voice_registry`: catálogo estático, `status="available"` sólo si existe un handler real en `tool_dispatch_service.py`). `AgentCompilerService` resuelve ambos hacia `RuntimeSessionSpecV1`: `settings` pasa tal cual dentro de `realtime`, y `tools` se recompila a `CompiledToolSpec` (`key/name/description/input_schema`, nunca `config`) como campo top-level separado — nunca dentro de `provider_overrides`, que ya bloquea `selectedTools` por diseño. El runtime (`voice-runtime/tool_dispatcher.py`) registra cada `CompiledToolSpec` como `RawFunctionTool` de `livekit-agents` en el `Agent(...)` de la sesión (sólo `serviglobal_managed`); el handler llama de vuelta a `POST /api/v1/internal/voice-runtime/sessions/{id}/tools/{key}/invoke` (mismo trust boundary `require_voice_runtime` que `/spec` y `/events`), que revalida el binding contra la versión publicada en base de datos y despacha por un allowlist literal de funciones Python (`app.services.tool_dispatch_service._HANDLERS`) hacia los servicios reales (`BookingService`, `WhatsAppMessageService`, `CrmContactService`/`CrmLeadService`) — nunca `eval` ni import dinámico desde algo que el modelo o el runtime provean.

**Session Context V1** provee la identidad de negocio que los handlers de tools usan en vez de confiar en argumentos de la LLM. `RuntimeSessionSpecV1.context` es `SessionContextV1` (`backend/app/schemas/session_context.py`, mirror manual en `voice-runtime/contracts.py`): `caller`/`contact`/`lead`/`campaign` separados explícitamente (caller = identidad telefónica de la llamada; contact = persona/organización conocida; lead = un proceso comercial que pertenece a un contact) más `variables` de negocio con límites explícitos (20 keys, 60 caracteres/key, profundidad 2, ~4KB serializado) y sin secretos. `ContactResolutionService` (`backend/app/services/contact_resolution_service.py`) es el único punto de resolución: `contact_id`/`lead_id` explícitos sólo si `trusted_ids=True` (nunca desde la LLM) → lookup por teléfono normalizado vía `voice_phone_service.normalize_caller_id` → sin resolver; nunca llama a `get_or_create_*` — un caller desconocido queda `contact=null`/`lead=null`, crear sigue siendo una acción explícita (p. ej. la tool `crm.create_lead`). El snapshot se persiste en `VoiceSession.session_context_json` (JSON nullable, sin tablas nuevas) al crear la sesión, y `AgentCompilerService.compile()` lo pasa tal cual a `RuntimeSessionSpecV1.context`. Hoy sólo está cableado al único punto real de creación de `VoiceSession` (`POST /api/v1/voice/sessions`, el flujo de prueba WebRTC) — inbound/outbound reales no existen conectados a Agent Builder. `ToolDispatchService.invoke()` carga este contexto y lo pasa a cada handler junto con `arguments`; los handlers que necesitan identidad (`calendar.create_booking`, `crm.create_lead`) la toman de `context.lead`/`context.contact`/`context.caller`, nunca de `arguments` — el `input_schema` visible a la LLM de esas tools ni siquiera declara `lead_id`/`contact_id`/`phone` como propiedades válidas.

`SessionContextV1` no es un objeto de estado arbitrariamente mutable: la única vía para cambiarlo después de creada la sesión es `VoiceSessionService.enrich_context()` (Fase F.1), que aplica **enriquecimiento monotónico controlado** — `unresolved → resolved` se permite, `resuelto → el mismo valor` es idempotente, `resuelto → un valor distinto` siempre falla cerrado (`SessionContextContactConflictError`/`SessionContextLeadConflictError`/`SessionContextTenantConflictError`, mensajes-código estables `session_context_contact_conflict`/`session_context_lead_conflict`/`session_context_tenant_conflict`). Existe porque `crm.create_lead` resuelve/crea un `Contact`/`Lead` a mitad de conversación y esa identidad debe quedar disponible para una tool posterior en la misma sesión (`calendar.create_booking`) sin que el LLM la provea nunca — el propio handler de `crm.create_lead` en `ToolDispatchService` es hoy el único integrador. `enrich_context()` recibe filas ORM (`CrmContact`/`CrmLead`), nunca IDs sueltos, valida `tenant_id` directamente contra ellas, nunca toca `caller`/`campaign`/`variables`/`source`, y reutiliza `ContactResolutionService.to_contact_context`/`to_lead_context` (públicos desde esta fase) para la misma representación segura que usa la resolución inicial. Emite `session.context.enriched` (mismo patrón sin PII que los demás eventos `session.context.*`).

Voice Runtime separa Control Plane y Data Plane. El backend fija la versión publicada, crea una Room determinista y despacha el job; `voice-runtime/` obtiene el spec por HTTP/JWT interno y ejecuta `AgentSession` con Ultravox, sin DB. El navegador recibe un token corto tenant-scoped para esa misma Room con grants de micrófono exclusivamente. El estado `connected` requiere el primer transcript final; agent ready, participante, entrada y salida de audio se registran como eventos detallados.

El outbound SIP de Sprint 7 usa el mismo Control Plane y Data Plane: LiveKit sigue siendo transporte/sesión y Ultravox el motor conversacional. El flujo crea primero `VoiceSession(channel="sip", direction="outbound")`, enlaza una única `CrmVoiceCall`, despacha el agente a la Room determinista y espera el evento persistido `voice.agent.ready`; sólo después `LiveKitSipService.create_sip_participant(..., wait_until_answered=true)` conecta el número por el `livekit_outbound_trunk_id` persistente de la ruta tenant. Nunca se crea un trunk por llamada. La persistencia correlaciona `voice_session_id`, `crm_voice_call_id`, Room, trunk, identidad del participante y `sip_call_id`; el número no se escribe en eventos ni logs. Ambos flags (`voice_runtime_v2` y `livekit_sip_outbound_v2`) son necesarios, por lo que deshabilitar cualquiera restaura la ruta legacy sin cambiar contratos existentes.

El PBX permanece como infraestructura SIP genérica. Los endpoints generados heredan de `serviglobal-tenant`; `ultravox-tenant` es sólo un alias de compatibilidad. Así, Asterisk no conoce el proveedor de IA: LiveKit origina SIP hacia el host/puerto y las credenciales cifradas de la ruta, mientras el runtime une al agente Ultravox en la misma Room. Estados SIP estructurados se proyectan a `busy`, `rejected`, `no_answer` o `failed`; cualquier fallo terminal intenta cerrar la Room para no dejar una sesión huérfana.

Las credenciales de proveedor de voz son tenant-scoped, no un `ULTRAVOX_API_KEY` global del contenedor `voice-runtime`. `voice-runtime` nunca almacena ni configura credenciales de proveedor: cada job las resuelve en tiempo de ejecución llamando a `GET /api/v1/internal/voice-runtime/sessions/{session_id}/credentials/{provider}` a través de `ControlPlaneCredentialResolver` (`voice-runtime/src/serviglobal_voice_runtime/credentials.py`), ligado al `session_id` del job — nunca a un `tenant_id` que el runtime pudiera enviar directamente. El Control Plane resuelve la `VoiceSession`, deriva su tenant, valida que el provider coincida con el de la sesión, y reutiliza `VoiceConfigService.get_active_provider_config`/`decrypt_api_key` sobre `TenantVoiceProviderConfig` (la misma fuente de verdad que usa la UI de Integraciones) para devolver la clave descifrada. La clave vive sólo en memoria durante el job; nunca aparece en `RuntimeSessionSpecV1`, metadata/tokens de LiveKit, eventos o logs. El contrato (`ProviderCredentialResolver`/`ProviderCredential` en `credentials.py`) es provider-agnostic: agregar ElevenLabs, OpenAI u otro proveedor no requiere cambiar la forma de la credencial ni el endpoint, sólo un adapter nuevo detrás del mismo `RealtimeProviderFactory`.

El rollback legacy obedece la misma frontera y resuelve la clave desde `TenantVoiceProviderConfig`; no existe fallback a `ULTRAVOX_API_KEY`. En `provider_managed`, el binding versionado guarda sólo el ID remoto y la revisión observada. Antes de cada ejecución, `UltravoxAgentCallFactory` vuelve a consultar el agente con la clave de la `VoiceSession`, clasifica tools, registra drift sin mutar la versión y crea una sola call con overrides allowlisted.

El subsistema de notificaciones separa administración (`notification_admin_service.py`), creación segura de eventos (`notification_event_pipeline.py`), planificación (`notification_orchestrator.py`), condiciones/destinatarios/variables, claims, reintentos, recuperación y ejecución WhatsApp. `backend/app/workers/notification_worker.py` procesa entregas vencidas fuera del proceso web y requiere PostgreSQL.

### Datos

PostgreSQL es la base principal. Alembic administra el esquema. Los dominios persistentes son identidad/tenant, llamadas/analítica, CRM, billing/uso, integraciones y notificaciones. Notificaciones usa `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events` y `notification_deliveries`. Los binarios de email se almacenan mediante `StorageService` en disco local o S3 compatible; la DB guarda metadata. Chatwoot es multi-tenant vía `tenant_chatwoot_configs` (una Account por tenant, `mode` external/managed, token cifrado, `webhook_key` único) y `tenant_chatwoot_inboxes` (inboxes adicionales opcionales); no hay tabla ni configuración global de credenciales por tenant. La excepción es `CHATWOOT_PLATFORM_API_TOKEN`: un token de Super Admin de la instancia compartida, global y fuera de `tenant_chatwoot_configs`, usado sólo por `ChatwootPlatformClient` para aprovisionar Accounts nuevas en modo managed (crea un usuario `administrator` dedicado por Account, no un Agent Bot — sus tokens no tienen permiso sobre la API de cuenta).

## Voice Provider Abstraction V1

El contrato versionado `AgentVoiceConfig` tiene dos rutas: `mode="provider"` selecciona una voz del catálogo Ultravox y llega a `RealtimeModel(voice=<id>)`; `mode="provider_external"` admite sólo ElevenLabs a través de Ultravox y llega a `RealtimeModel(external_voice={"elevenLabs": ...})`. El runtime no envía `voice` y `external_voice` juntos. Para ElevenLabs son obligatorios `voice_id` y `settings.model` (string libre no vacío, máximo 80 caracteres); `speed`, `stability`, `similarity_boost` y `use_speaker_boost` son opcionales.

El draft se valida localmente, sin I/O. El preview genera audio sólo por acción explícita y puede consumir cuota. Publish realiza un preflight remoto sin generar audio: consulta metadata de la voz de catálogo o confirma BYOK ElevenLabs mediante un `prefix` no vacío en la cuenta Ultravox del tenant. El runtime repite la validación defensiva antes de construir opciones LiveKit. ServiGlobal conserva únicamente la clave Ultravox tenant-scoped; no gestiona una clave ElevenLabs directa.

## Límites de confianza

- Auth0 autentica la aplicación privada; el backend resuelve usuario, membresía, rol y tenant.
- Las rutas tenant derivan `tenant_id` del contexto autenticado.
- Las rutas `/api/v1/admin/...` requieren autorización de plataforma y pueden seleccionar tenant explícitamente.
- La familia `/api/v1/admin/notifications` es una excepción nominal: también admite roles tenant. Toda operación sobre recursos deriva el tenant de `AuthContext`; el catálogo común sigue autenticado y ningún endpoint acepta `tenant_id` del body o query.
- Webhooks verifican firma o secreto cuando el proveedor lo soporta. Chatwoot no firma sus webhooks salientes: el aislamiento por tenant usa un `webhook_key` opaco en la URL (`POST /api/v1/webhooks/chatwoot/{webhook_key}`) más un cross-check de `payload.account.id` contra la Account configurada.
- Herramientas internas de voz usan secreto compartido y nunca aceptan un tenant arbitrario sin resolver contexto seguro.
- Los secretos por tenant se cifran; las respuestas sólo indican presencia mediante campos como `has_secret`.

## Flujos principales

### Prueba WebRTC de agente

1. Un administrador tenant crea una `VoiceSession` `webrtc`; el backend deriva tenant y fija la versión publicada.
2. LiveKit crea el dispatch en `sg-vs-{session_id}` y el runtime obtiene `RuntimeSessionSpecV1`.
3. El navegador obtiene un token room-scoped, entra a esa misma Room y publica un único micrófono.
4. El runtime ignora al participant agente, registra al humano y `AgentSession` entrega su audio a Ultravox.
5. El primer transcript final marca la sesión `connected`; la respuesta vuelve como track LiveKit y el browser la reproduce.
6. Al colgar, participante, adapter, `AgentSession` y modelo liberan recursos y la sesión termina. Sin participante, el runtime aplica timeout configurable.

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
