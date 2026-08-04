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
| `/api/v1/voice` | Inicio de llamadas y operación de voz. |
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
| `GET /catalog` | Eventos, capacidades, estrategias, operadores, fuentes, formatos y modos permitidos. |
| `GET /capabilities` | Lista capacidades del tenant. |
| `PATCH /capabilities/{capability_key}` | Activa o desactiva una capacidad. |
| `GET /rules` | Lista reglas y su posible `configuration_error`. |
| `POST /rules` | Crea una regla validada. |
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
- Evento, capacidad, estrategia, condiciones, destinatario y variables deben pertenecer al catálogo permitido.
- Una plantilla WhatsApp debe estar activa, sincronizada desde Meta y `APPROVED`.
- Todos los parámetros requeridos por la plantilla deben tener un mapeo efectivo.
- Una regla con entregas asociadas no se elimina; el servicio devuelve `rule_has_deliveries`.

## Convenciones

- IDs son strings opacos; no deben inferirse ni reutilizarse entre tenants.
- Errores de proveedor se sanitizan antes de responder o persistir.
- Las operaciones externas pueden devolver estado de negocio `failed` aun con una respuesta HTTP válida; consulte el schema.
- Webhooks pueden reintentarse y deben tratarse como idempotentes.
