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
| `/api/v1/agents` | Agent Builder tenant: borradores, publicación, despublicación, archivo y eliminación segura. |
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

## Agent Builder

- `POST /api/v1/agents/{agent_id}/publish` publica el borrador actual como versión inmutable. Para `serviglobal_managed` con voz configurada, valida primero sin generar audio: `mode="provider"` confirma que la voz sigue accesible (`404`/`409` del proveedor → `voice_not_accessible`); `mode="provider_external"` confirma que la cuenta Ultravox del tenant tiene BYOK del proveedor externo vía `/accounts/me/tts_api_keys` (`external_tts_credentials_unavailable` si falta). También revalida cada tool `enabled` en `tools[]`: confirma que siga siendo un tool `status="available"` del Registry (`tool_not_found`/`tool_not_available` si no) y que el tenant tenga configurada la integración que requiere (`tool_integration_not_configured` si no, reutilizando la resolución real del servicio — `BookingService`/`WhatsAppConfigService` — nunca sólo una comprobación superficial). `provider_managed` conserva su propio preflight sin cambios.
- `POST /api/v1/agents` y `PATCH .../draft` aceptan `voice: {mode, provider, voice_id, settings}` (`AgentVoiceConfig`) para `serviglobal_managed`; se rechaza si `management_mode="provider_managed"`. Validado localmente sin red: forma/secretos en el schema, compatibilidad de registry y allowlist de `settings` (sólo `provider_external`+`elevenlabs`: `model`, `speed`, `stability`, `similarity_boost`, `use_speaker_boost`) en `VoiceSelectionService`. Sin `voice`, un `TenantVoiceAgentConfig.default_voice` legacy vinculado sigue funcionando sin migración.
- `POST /api/v1/agents` y `PATCH .../draft` también aceptan `settings: {...}` (parámetros de modelo, p.ej. `temperature`) validados sin red contra `voice_registry.validate_model_settings()` según el `(provider, model)` elegido, y `tools: [{key, enabled, config}]` validados sin red contra `app.domain.tool_registry.validate_tool_bindings()` (rechaza `key` desconocida, `status="planned"`, o duplicada). Ambos se rechazan si `management_mode="provider_managed"`. Sin `settings`/`tools`, el agente compila igual que antes (compatibilidad retroactiva total).
- `GET /api/v1/agents/tools/catalog` (roles de lectura, no ligado a un `agent_id`) devuelve el catálogo completo de `app.domain.tool_registry` anotado con `available: bool` por tenant — `true` sólo para tools `status="available"` cuya `required_integration` esté configurada (misma resolución real que usa el preflight de publish). Las tools `status="planned"` siempre reportan `available=false`.
- `POST /api/v1/agents/{agent_id}/unpublish` retira la versión activa y crea o conserva un borrador editable con toda su configuración.
- `POST /api/v1/agents/{agent_id}/archive` deja el agente en solo lectura.
- `POST /api/v1/agents/{agent_id}/delete` elimina definitivamente un agente archivado y sus versiones. Conserva sesiones/eventos e IDs históricos (`deleted_agent_id`, `deleted_agent_version_id`). Las sesiones no terminales se cancelan tras confirmar que su sala LiveKit se cerró; si el dispatch aún no tiene sala o el cierre no puede verificarse, devuelve `409` (`agent_delete_session_dispatching`, `agent_delete_room_close_failed` o `agent_delete_session_unverified`) y conserva el agente. Un agente no archivado responde `409` con `agent_delete_requires_archived`. `DELETE /api/v1/agents/{agent_id}` se conserva por compatibilidad.
- `/api/v1/integrations/voice/providers/{provider}/agents` y `.../voices` exponen catálogos tenant-scoped con cursores opacos. `POST .../agents/{agent_id}/import` crea un agente/draft independiente. `GET .../voices/{voice_id}/preview` valida primero el recurso y siempre obtiene la muestra del endpoint de preview; nunca se exponen `definition` ni `previewUrl`. `{provider}` se resuelve vía `voice_provider_admin.get_provider_admin_service`, que solo despacha a proveedores `status="active"` en `voice_registry.py` con un adapter real registrado; hoy únicamente `ultravox`. Cualquier otro valor responde `404 provider_not_available`.
- `POST .../providers/ultravox/external-voice/preview` (roles de escritura: genera audio, potencialmente facturable) recibe el contrato ServiGlobal (`mode="provider_external"`, `provider="elevenlabs"`, `voice_id`, `settings`), lo valida localmente, construye `definition.elevenLabs` con un mapper explícito y llama `POST /api/voice_preview` de Ultravox con la API key Ultravox tenant-scoped (un único intento, sin retry). Responde `audio/wav`, `Cache-Control: private, no-store`, sin persistir nada; ServiGlobal nunca resuelve ni almacena una credencial ElevenLabs propia.
- Agent Builder acepta `management_mode=provider_managed` con `provider_agent.agent_id`; `observed_published_revision_id` se guarda sólo en el binding versionado. Bindings sin modo se interpretan como `serviglobal_managed`.
- Todas las rutas derivan el tenant de `AuthContext`; las mutaciones requieren `platform_admin` o `tenant_admin`.

## Integraciones destacadas

- `GET /api/v1/integrations/availability` lista los providers habilitados para el tenant; `GET /api/v1/integrations/statuses` devuelve únicamente `{provider, status}` para el catálogo (`active|configured|not_configured|error`), sin credenciales, IDs de recursos, listas ni PII.
- `GET /api/v1/admin/tenants/{tenant_id}/integrations/statuses` ofrece el mismo contrato compacto al administrador interno para Resend, WhatsApp, voz, Cal.com, Google Calendar y Chatwoot. Exige acceso interno, conserva visibles las integraciones aunque estén deshabilitadas y no devuelve secretos, configuración ni PII.
- Chatwoot replica `config`, `test` y `provision` para el administrador interno bajo `/api/v1/admin/tenants/{tenant_id}/integrations/chatwoot`, siempre derivando el tenant del parámetro de la ruta validado por acceso interno.
- Resend: configuración, test, templates y assets bajo `/api/v1/integrations/resend`.
- Cal.com: configuración, test y slots bajo `/api/v1/integrations/calcom`; bookings viven en CRM.
- Google Calendar: connect URL, callback, connections y disconnect.
- WhatsApp: configuración, test, sync masivo de templates aprobados en Meta y ciclo de vida completo de templates propios (`GET|POST /whatsapp/templates`, `GET|PATCH|DELETE /whatsapp/templates/{id}`, `GET .../preview`, `POST .../submit`, `POST .../sync-status`); replicado bajo `/api/v1/admin/tenants/{tenant_id}/integrations/whatsapp/templates...` para `platform_admin`. Los botones de un template admiten `QUICK_REPLY|URL|PHONE_NUMBER|VOICE_CALL|FLOW`; `VOICE_CALL` sólo se acepta (backend, 422 si no) y sólo debe ofrecerse en UI cuando `GET .../whatsapp/config` responde `voice_calling_enabled: true`, feature controlada por `platform_admin` vía `PUT /api/v1/admin/tenants/{tenant_id}/features/whatsapp-business-calling`.
- WhatsApp Flow Studio: `GET|POST /api/v1/integrations/whatsapp/flows`, `GET|PATCH|DELETE /flows/{flow_id}` y acciones `POST /compile`, `/sync-meta`, `/sync-status`, `/publish`, `/clone` y `/deprecate`. Lectura: roles tenant de lectura; escritura: `platform_admin` y `tenant_admin`. Todas las rutas derivan el tenant de `AuthContext`, usan la configuración WhatsApp existente y nunca aceptan `tenant_id` ni credenciales Meta desde el frontend. Sólo borradores pueden editarse/eliminarse; una publicación crea una versión inmutable y `/clone` abre la siguiente versión editable.
- Voz: configuración, test, agentes y ruta SIP saliente por tenant. El backend deriva `sip_username` del ID de la ruta y no acepta un usuario elegido por el cliente; la respuesta lo devuelve para configuración operativa y sólo indica si existe contraseña SIP, sin devolver el secreto.
- `POST /api/v1/crm/leads/{lead_id}/actions/call` mantiene `{agent_config_id}` para el runtime legacy. Cuando `voice_runtime_v2` y `livekit_sip_outbound_v2` están habilitados exige `{agent_id, idempotency_key}`; deriva tenant, contacto, destino y ruta desde recursos persistidos, crea la sesión SIP/outbound y responde con `voice_call_id`, `voice_session_id`, `provider_call_id` y `sip_call_id`. Un mismo `idempotency_key` del tenant no vuelve a originar una llamada. Errores de capacidad, país, ruta, agente, readiness o SIP responden `422` con códigos sanitizados y sin números o credenciales.
- Chatwoot (multi-tenant, modo "external" o "managed"): `GET|POST /api/v1/integrations/chatwoot/config`, `POST /api/v1/integrations/chatwoot/test` y `POST /api/v1/integrations/chatwoot/provision`. La respuesta nunca incluye el access token (sólo `has_secret`); expone `mode` (`external`|`managed`) y `webhook_url` (path relativo con el `webhook_key` opaco del tenant) para que el operador lo configure en Chatwoot → Settings → Integrations → Webhooks (en `managed` ese webhook de cuenta se registra automáticamente vía Platform API, sin paso manual). `POST .../provision` (body opcional `{account_name}`, por defecto el nombre del tenant) crea, vía la Platform API de Chatwoot, una Account + un usuario `administrator` dedicado (no un Agent Bot: sus tokens no tienen permiso sobre `/api/v1/accounts/*`) + un inbox `api` + el webhook de cuenta, y deja el tenant en modo `managed`; devuelve 422 si ya hay una integración activa, si `CHATWOOT_PLATFORM_API_TOKEN`/`BACKEND_PUBLIC_BASE_URL` no están configurados, o si la Platform API falla (mensaje saneado, nunca HTML/tokens crudos). Webhook entrante tenant-aware: `POST /api/v1/webhooks/chatwoot/{webhook_key}` (sin auth de sesión; resuelve el tenant por `webhook_key` y valida `payload.account.id` contra el `account_id` configurado — 404 si el key no existe, 401 si el `account_id` no coincide). Chatwoot no firma sus webhooks salientes de forma nativa, por lo que el `webhook_key` opaco es el mecanismo primario de aislamiento entre tenants.

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

## Voice Runtime WebRTC

| Método y ruta | Uso |
| --- | --- |
| `POST /api/v1/voice/sessions` | Crea una `VoiceSession` para el agente publicado del tenant autenticado y ejecuta el dispatch LiveKit. Para browser usa `{agent_id, channel: "webrtc", direction: "internal", idempotency_key}`; no acepta `tenant_id` ni room. Acepta además `contact_id`/`lead_id`/`caller_phone` opcionales (confiables sólo porque este endpoint exige `WRITE_ROLES`, nunca un pass-through de input no autenticado): se resuelven vía `ContactResolutionService` y quedan snapshoteados en `session_context_json`, compilado luego a `RuntimeSessionSpecV1.context`. `lead_id`/`contact_id` cruzando tenant devuelven `422`. |
| `POST /api/v1/voice/sessions/{session_id}/webrtc-token` | Emite un token LiveKit de máximo 10 minutos, limitado a `session.livekit_room_name`, subscribe y publicación exclusiva de micrófono. Rechaza sesiones ajenas, terminales, sin room o con runtime distinto de LiveKit. |
| `GET /api/v1/internal/voice-runtime/sessions/{session_id}/spec` | Entrega `RuntimeSessionSpecV1` al runtime autenticado por JWT interno; nunca incluye secretos. |
| `GET /api/v1/internal/voice-runtime/sessions/{session_id}/credentials/{provider}` | Resuelve la credencial del proveedor de voz para el tenant dueño de esa `VoiceSession`, descifrada desde `TenantVoiceProviderConfig`. Ligado a `session_id`, no a un `tenant_id` enviado por el runtime; rechaza sesión inexistente o provider no asociado (`404`), provider desconocido (`422`) e integración inactiva o sin API key (`409`). |
| `POST /api/v1/internal/voice-runtime/sessions/{session_id}/events` | Persiste eventos runtime idempotentes y sanitizados; sólo started/connected/ended/failed cambian el estado principal. |
| `POST /api/v1/internal/voice-runtime/sessions/{session_id}/tools/{tool_key}/invoke` | Ejecuta una tool para esa sesión. Revalida el binding contra la versión publicada real en base de datos (nunca confía en lo que el runtime dice haber compilado), valida `arguments` contra el `input_schema` del tool y despacha por un allowlist literal de handlers (`app.services.tool_dispatch_service._HANDLERS`, nunca `eval`/import dinámico). Handlers que necesitan identidad (`calendar.create_booking`, `crm.create_lead`) la toman de `SessionContextV1` (cargado desde `session.session_context_json`), nunca de `arguments` — `lead_id`/`contact_id`/`phone` ni siquiera son propiedades válidas en el `input_schema` visible a la LLM de esas tools. `crm.create_lead` además enriquece `session.session_context_json` con el Contact/Lead recién resuelto (`VoiceSessionService.enrich_context`, enriquecimiento monotónico controlado — nunca reemplaza una identidad ya resuelta, ver `docs/ARCHITECTURE.md`), disponible para un `calendar.create_booking` posterior en la misma sesión sin que el LLM provea `lead_id`. Errores: `404` tool no vinculada, `422` tool no disponible o argumentos inválidos, `502` fallo del handler real (incluye `lead_context_required`/`caller_phone_required` cuando falta el contexto necesario, y `session_context_contact_conflict`/`session_context_lead_conflict`/`session_context_tenant_conflict` cuando el enriquecimiento detecta una identidad en conflicto), `409` sesión terminal. Responde `{"result": {...}}`; nunca incluye `config` del binding. |

El evento `voice.agent.ready` además fija `runtime_ready_at`; ésta es la barrera que usa el outbound SIP antes de marcar. La respuesta del token contiene `voice_session_id`, `server_url`, `room_name`, `participant_token` y `expires_in`. El participant token es sensible y efímero: no se registra ni se persiste. Las rutas tenant derivan el tenant de `AuthContext`; las internas no aceptan `tenant_id`. La credencial del proveedor sólo viaja por este endpoint interno autenticado hacia `voice-runtime`; nunca aparece en `RuntimeSessionSpecV1`, metadata de LiveKit, eventos o logs.

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
