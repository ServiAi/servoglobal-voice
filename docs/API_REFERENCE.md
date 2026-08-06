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

- `GET /api/v1/crm/pipeline`, `/leads`, `/leads/{lead_id}`, `/pipeline/board`.
- `PATCH /api/v1/crm/leads/{lead_id}` y `/stage`.
- `GET|POST|PATCH|DELETE /api/v1/crm/tasks...`.
- `POST /api/v1/crm/leads/{lead_id}/bookings` y acciones de cancelación/reprogramación.
- `POST /api/v1/crm/leads/{lead_id}/actions/email`.
- `POST /api/v1/crm/leads/{lead_id}/actions/whatsapp` y `GET .../messages`.
- `POST /api/v1/crm/leads/{lead_id}/actions/call` y `GET .../calls`.
- `GET /api/v1/crm/leads/{lead_id}/call-summary` y generación de asset.

## Integraciones destacadas

- Resend: configuración, test, templates y assets bajo `/api/v1/integrations/resend`.
- Cal.com: configuración, test y slots bajo `/api/v1/integrations/calcom`; bookings viven en CRM.
- Google Calendar: connect URL, callback, connections y disconnect.
- WhatsApp: configuración, test y templates.
- Voz: configuración, test y agentes.

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
- Una plantilla WhatsApp debe estar activa, sincronizada desde Meta y `APPROVED`.
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
| `GET/POST /api/v1/voice/experiences` | Lista las experiencias del tenant o crea un draft. |
| `GET/PUT /api/v1/voice/experiences/{experience_id}` | Consulta o reemplaza el draft mutable sin alterar snapshots publicados. |
| `POST /api/v1/voice/experiences/{experience_id}/publish` | Publica un snapshot inmutable nuevo; exige schema `active`. |
| `POST /api/v1/voice/experiences/{experience_id}/unpublish` | Despublica la experiencia sin eliminar su historial. |
| `POST /api/v1/voice/experiences/{experience_id}/archive` | Archiva una experiencia no publicada y libera capacidad. |
| `GET /api/v1/voice/experiences/{experience_id}/versions` | Lista snapshots publicados inmutables. |

El tenant se deriva de `AuthContext`; los bodies rechazan `tenant_id`. Lectura: plataforma interna y roles tenant de lectura. Escritura: plataforma interna y `tenant_admin`. La feature `voice_experiences` debe estar habilitada. `max_context_fields` sólo limita campos de schemas; `max_experiences` cuenta experiencias cuyo estado no sea `archived`. Los slugs se generan en servidor y las respuestas no exponen prompts, tools, secretos de proveedor, credenciales SIP ni PII interna.

Estos endpoints son exclusivamente autenticados y alimentan el builder privado de CRM en `/{locale}/crm/settings/voice-experiences`. Todavía no existen página o formulario público, tokens públicos, context submission ni runtime WebRTC para Voice Experiences.

## Convenciones

- IDs son strings opacos; no deben inferirse ni reutilizarse entre tenants.
- Errores de proveedor se sanitizan antes de responder o persistir.
- Las operaciones externas pueden devolver estado de negocio `failed` aun con una respuesta HTTP válida; consulte el schema.
- Webhooks pueden reintentarse y deben tratarse como idempotentes.
