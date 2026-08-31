# Referencia de API

La especificación ejecutable completa está disponible en `/docs` y `/openapi.json` cuando FastAPI está en ejecución. Esta guía resume las familias estables; los schemas del código son la autoridad para payloads y respuestas.

## Acceso

- Público: landing, formularios por token y verificaciones/webhooks necesarios.
- Tenant: bearer token Auth0; el tenant se obtiene del contexto, no del body.
- Admin: rutas `/api/v1/admin/...` con rol de plataforma.
- Interno/proveedor: firma, webhook secret o shared secret según integración.

## Familias

| Prefijo | Propósito |
| --- | --- |
| `/api/v1/me` | Usuario, rol y tenant activos. |
| `/api/v1/dashboard` | KPIs, tendencias, distribuciones, heatmap, llamadas, uso y ahorro. |
| `/api/v1/crm` | Pipeline, leads, detalle, bookings, notas, tareas, métricas, email, WhatsApp y llamadas. |
| `/api/v1/integrations` | Resend, Cal.com, Google Calendar, WhatsApp y voz por tenant. |
| `/api/v1/forms` | Definiciones y tokens de formularios tenant. |
| `/api/v1/public/forms` | Lectura y envío público mediante token opaco. |
| `/api/v1/admin` | Tenants, planes, uso, membresías, agentes e integraciones administradas. |
| `/api/v1/admin/notifications` | Administración tenant de capacidades, reglas, destinatarios y entregas. El tenant se deriva del contexto autenticado. |
| `/api/v1/admin/tenants/{tenant_id}/features` | Grants de funcionalidades por tenant para administradores de plataforma. |
| `/api/v1/voice` | Inicio de llamadas, operación de voz, context schemas y administración privada de Voice Experiences. |
| `/api/v1/voice/tools` | Disponibilidad y booking para agentes internos protegidos. |
| `/api/v1/webhook/whatsapp` | Verificación y eventos Meta. |
| `/api/v1/calcom/webhook` | Reconciliación Cal.com. |

## Operaciones CRM destacadas

- `GET /api/v1/crm/dashboard` incluye `voice_capacity`: ocupación y cupos actuales de la ruta SIP, estado de ruta/aprovisionamiento y hasta diez saturaciones o recuperaciones del período. El tenant se deriva de `AuthContext`; fuente y campaña no alteran esta sección.
- `GET /api/v1/crm/pipeline`, `/leads`, `/leads/{lead_id}`, `/pipeline/board`.
- `PATCH /api/v1/crm/leads/{lead_id}` y `/stage`.
- `GET|POST|PATCH|DELETE /api/v1/crm/tasks...`.
- `POST /api/v1/crm/leads/{lead_id}/bookings` y acciones de cancelación/reprogramación.
- `POST /api/v1/crm/leads/{lead_id}/actions/email`.
- `POST /api/v1/crm/leads/{lead_id}/actions/whatsapp` y `GET .../messages`.
- `POST /api/v1/crm/leads/{lead_id}/actions/call` y `GET .../calls`.
- `GET /api/v1/crm/leads/{lead_id}/call-summary` y generación de asset.

## Integraciones destacadas

- `GET /api/v1/integrations/availability` lista los providers habilitados para el tenant; `GET /api/v1/integrations/statuses` devuelve únicamente `{provider, status}` para el catálogo (`active|configured|not_configured|error`), sin credenciales, IDs de recursos, listas ni PII.
- Resend: configuración, test, templates y assets bajo `/api/v1/integrations/resend`.
- Cal.com: configuración, test y slots bajo `/api/v1/integrations/calcom`; bookings viven en CRM.
- Google Calendar: connect URL, callback, connections y disconnect.
- WhatsApp: configuración, test, sync masivo de templates aprobados en Meta y ciclo de vida completo de templates propios (`GET|POST /whatsapp/templates`, `GET|PATCH|DELETE /whatsapp/templates/{id}`, `GET .../preview`, `POST .../submit`, `POST .../sync-status`); replicado bajo `/api/v1/admin/tenants/{tenant_id}/integrations/whatsapp/templates...` para `platform_admin`. Los botones de un template admiten `QUICK_REPLY|URL|PHONE_NUMBER|VOICE_CALL|FLOW`; `VOICE_CALL` sólo se acepta (backend, 422 si no) y sólo debe ofrecerse en UI cuando `GET .../whatsapp/config` responde `voice_calling_enabled: true`, feature controlada por `platform_admin` vía `PUT /api/v1/admin/tenants/{tenant_id}/features/whatsapp-business-calling`.
- Voz: configuración, test, agentes y ruta SIP saliente por tenant. El backend deriva `sip_username` del ID de la ruta y no acepta un usuario elegido por el cliente; la respuesta lo devuelve para configuración operativa y sólo indica si existe contraseña SIP, sin devolver el secreto.

## Administración de automatizaciones y notificaciones

Prefijo: `/api/v1/admin/notifications`.

Aunque el prefijo contiene `admin`, las lecturas admiten `platform_admin`, `tenant_admin`, `tenant_analyst` y `tenant_viewer`; las escrituras sólo admiten `platform_admin` y `tenant_admin`. Toda operación sobre recursos tenant usa `context.tenant.id` y no acepta un `tenant_id` arbitrario. El catálogo es común, pero exige el mismo contexto autenticado de lectura.

| Método y ruta | Propósito |
| --- | --- |
| `GET /overview` | Conteos de capacidades, reglas, destinatarios y entregas por estado. |
| `GET /catalog` | Catálogo completo: capacidades, contratos versionados de eventos, campos tipados, operadores, ejemplos, estrategias y formatos. |
| `GET /catalog/capabilities` | Metadata de capacidades y sus eventos disponibles. |
| `GET /catalog/capabilities/{capability_key}/events` | Contratos de eventos de una capacidad. |
| `GET /catalog/capabilities/{capability_key}/events/{event_type}` | Contrato versionado, campos y payload de ejemplo de un evento. |
| `GET /capabilities` | Lista capacidades del tenant. |
| `PATCH /capabilities/{capability_key}` | Activa o desactiva una capacidad. |
| `GET /rules` | Lista reglas y su posible `configuration_error`. |
| `POST /rules` | Crea una regla validada. |
| `POST /rules/test` | Evalúa condiciones, variables, destinatarios enmascarados y preview con un payload de prueba; no crea entregas ni envía mensajes. |
| `PATCH /rules/{rule_id}` | Actualiza una regla del tenant. |
| `PATCH /rules/{rule_id}/enabled` | Activa o desactiva una regla. |
| `DELETE /rules/{rule_id}` | Elimina una regla sin entregas asociadas; responde `204`. |
| `GET /recipients` | Lista grupos/destinatarios con destino enmascarado. |
| `POST /recipients` | Crea un destinatario validado. |
| `PATCH /recipients/{recipient_id}` | Actualiza datos, destino opcional o estado. |
| `GET /deliveries` | Lista paginada y filtrable de entregas. |
| `GET /deliveries/{delivery_id}` | Devuelve detalle seguro de una entrega. |

`GET /deliveries` acepta `page`, `page_size`, `status_filter`, `event_type`, `rule_id`, `date_from`, `date_to`, `scheduled_from` y `scheduled_to`. Las respuestas muestran destinatarios enmascarados y omiten payloads internos, secretos y tokens de claim.

Validaciones relevantes:

- Nombres de reglas duplicados producen conflicto.
- Capacidad y evento deben formar una pareja registrada; las rutas, operadores, valores y formatos se validan contra el mismo contrato que consume el runtime.
- `conditions_mode` admite `all` y `any`. Una regla sin condiciones coincide en ambos modos.
- Una plantilla WhatsApp debe tener `status="approved"` (sincronizada desde Meta o creada en la app, enviada y aprobada).
- Todos los parámetros requeridos por la plantilla deben tener un mapeo efectivo.
- Una regla con entregas asociadas no se elimina; el servicio devuelve `rule_has_deliveries`.
- El dry-run sólo acepta payloads conformes al contrato del evento y nunca persiste `DomainEvent` o `NotificationDelivery`.
- Crear, actualizar, activar, desactivar, eliminar o probar una regla genera un `AccessAuditLog` con acción y referencia técnica; no guarda el payload, variables, preview ni destinatarios.

## Administración de funcionalidades tenant

Los endpoints requieren `context.user.is_internal == true`; ningún rol de membresía tenant, incluido `platform_admin`, concede acceso. Además validan que el tenant objetivo exista.

| Método y ruta | Propósito |
| --- | --- |
| `GET /api/v1/admin/tenants/{tenant_id}/features` | Lista grants persistidos del tenant. |
| `PUT /api/v1/admin/tenants/{tenant_id}/features/voice-experiences` | Crea o actualiza `voice_experiences` con `enabled`, `max_experiences` y `max_context_fields`. |

La respuesta omite el identificador del tenant, el usuario que realizó el cambio y cualquier dato sensible.

## Voice Context Experiences

| Método y ruta | Uso |
| --- | --- |
| `GET/POST /api/v1/voice/agents/{agent_config_id}/context-schemas` | Lista lineages o crea un draft para el agente autenticado. |
| `GET /api/v1/voice/agents/{agent_config_id}/context-schemas/{schema_key}/versions` | Consulta el historial completo del lineage. |
| `GET/PUT /api/v1/voice/context-schemas/{schema_id}` | Consulta o edita metadata draft. |
| `POST /api/v1/voice/context-schemas/{schema_id}/fields` | Agrega un campo a un draft. |
| `PUT/DELETE /api/v1/voice/context-schemas/{schema_id}/fields/{field_id}` | Edita o elimina un campo draft. |
| `POST /api/v1/voice/context-schemas/{schema_id}/activate` | Activa el draft y archiva la active anterior del lineage. |
| `POST /api/v1/voice/context-schemas/{schema_id}/archive` | Archiva un draft o active. |
| `POST /api/v1/voice/context-schemas/{schema_id}/new-version` | Clona una versión inmutable a un nuevo draft. |
| `DELETE /api/v1/voice/context-schemas/{schema_id}` | Elimina únicamente un schema archivado sin referencias actuales ni históricas; una referencia responde `409` y nunca elimina experiencias o snapshots. |
| `GET/POST /api/v1/voice/experiences` | Lista las experiencias del tenant o crea un draft. |
| `GET/PUT /api/v1/voice/experiences/{experience_id}` | Consulta o reemplaza el draft mutable sin alterar snapshots publicados. |
| `POST /api/v1/voice/experiences/{experience_id}/publish` | Publica la experiencia: crea un snapshot inmutable (estado `published`) disponible en la ruta pública; exige schema `active`. |
| `POST /api/v1/voice/experiences/{experience_id}/unpublish` | Despublica la experiencia sin eliminar su historial. |
| `POST /api/v1/voice/experiences/{experience_id}/archive` | Archiva una experiencia no publicada y libera capacidad. |
| `DELETE /api/v1/voice/experiences/{experience_id}` | Elimina físicamente una experiencia archivada y, en la misma transacción, sus versiones, submissions, valores, sesiones de contexto y runtime asociados. Conserva la auditoría CRM e integration events. Los demás estados responden `409`. |
| `GET /api/v1/voice/experiences/{experience_id}/versions` | Lista snapshots inmutables e indica `can_delete`/`delete_block_reason` para cada versión. |
| `DELETE /api/v1/voice/experiences/{experience_id}/versions/{version_id}` | Elimina una versión histórica no actual, no reciente y sin submissions, sesiones o llamadas asociadas. Deriva el tenant de `AuthContext`, conserva la numeración monotónica y responde `409` cuando la eliminación está bloqueada. |
| `GET /api/v1/public/voice-experiences/{slug}` | Resuelve sin autenticación exclusivamente el snapshot publicado exacto y su schema histórico. Devuelve un DTO público sanitizado y `Cache-Control: no-store`; cualquier estado no publicable responde un `404` genérico. `theme` incluye `logo_url`, `primary_color`, `background_color`, `color_scheme` (`light` por defecto para snapshots previos a esta funcionalidad) y `layout`. La misma ruta se sirve tanto en `/{locale}/voice/{slug}` como en `/{locale}/voice/{slug}/embed` (frontend); esta última es la única con `Content-Security-Policy: frame-ancestors *` para permitir su uso en `<iframe>`. |
| `POST /api/v1/public/voice-experiences/{slug}/submissions` | Sin Auth0. Consume rate limit global antes del JSON, valida envelope/campos/consentimiento, verifica Turnstile y persiste submission, values y context session 1:1 contra la versión exacta. Proyecta contact, lead y activity CRM por `context_id`; devuelve token efímero sin IDs internos, con `submissions=true`, `calls=true`. |
| `POST /api/v1/public/voice-experiences/{slug}/calls` | Sin Auth0. Acepta sólo `context_token`, aplica rate limits, recovery-first y claim one-shot; resuelve configuración/agente Ultravox tenant, devuelve `join_url` efímero y nunca expone IDs/provider/prompt/tools. |
| `POST /api/v1/public/voice-experiences/{slug}/callback-requests` | Sin Auth0. Acepta sólo `context_token`, valida consentimiento, teléfono, país, ruta SIP y capacidad del tenant; crea un `CrmVoiceCall` idempotente y responde `202` sin exponer tenant, número, agente ni proveedor. |
| `GET /api/v1/internal/asterisk/desired-state` | Interno. Exige `X-Asterisk-Provisioner-Secret`, responde `no-store` y entrega al agente del PBX el snapshot completo de endpoints PJSIP deseados. Es el único contrato que devuelve la contraseña SIP descifrada. |
| `POST /api/v1/internal/asterisk/apply-results` | Interno. Exige el mismo secreto dedicado; confirma o falla revisiones exactas e ignora resultados obsoletos. No acepta `tenant_id`, Caller ID ni rutas arbitrarias. |

Los context schemas usados por `TenantVoiceExperienceVersion` forman parte del contrato reproducible de la publicación. Aunque una experiencia cambie su borrador a otro schema, el schema histórico no puede eliminarse mientras un snapshot lo referencie. La política de retención puede evolucionar posteriormente; el historial actual se conserva.

El tenant se deriva de `AuthContext`; los bodies rechazan `tenant_id`. Lectura: plataforma interna y roles tenant de lectura. Escritura: plataforma interna y `tenant_admin`. La feature `voice_experiences` debe estar habilitada. `max_context_fields` sólo limita campos de schemas; `max_experiences` cuenta experiencias cuyo estado no sea `archived`. Los slugs se generan en servidor y las respuestas no exponen prompts, tools, secretos de proveedor, credenciales SIP ni PII interna.

Reglas de dominio: `PUT` rechaza con `409` cambiar `agent_config_id` cuando ya existe historial de versiones. El estado persistido `published` representa un snapshot inmutable. Restaurar una versión copia su snapshot al borrador; no modifica el historial. Cualquier versión seleccionada puede eliminarse si no es la versión pública actual, no tiene referencias y la experiencia no está archivada. El endpoint público exige estado `published`, referencia exacta `published_version_id`, feature tenant habilitada y coincidencia de experiencia/tenant/schema; ante cualquier inconsistencia falla cerrado.

Los endpoints administrativos bajo `/api/v1/voice` siguen autenticados. La superficie pública permite lectura, context submission y, según la versión publicada, inicio one-shot de WebRTC o solicitud de callback saliente; la demo heredada `/api/v1/calls` continúa separada. El DTO no expone tenant, proveedor, prompt, tools o credenciales. Las llamadas usan errores cerrados `404/409/410/422/429/503/500`, siempre `no-store`. Ver `docs-local/fase-4/VOICE_EXPERIENCE_WEBRTC_RUNTIME.md`.

## Convenciones

- IDs son strings opacos; no deben inferirse ni reutilizarse entre tenants.
- Errores de proveedor se sanitizan antes de responder o persistir.
- Las operaciones externas pueden devolver estado de negocio `failed` aun con una respuesta HTTP válida; consulte el schema.
- Webhooks pueden reintentarse y deben tratarse como idempotentes.
