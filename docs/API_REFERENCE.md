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

## Convenciones

- IDs son strings opacos; no deben inferirse ni reutilizarse entre tenants.
- Errores de proveedor se sanitizan antes de responder o persistir.
- Las operaciones externas pueden devolver estado de negocio `failed` aun con una respuesta HTTP válida; consulte el schema.
- Webhooks pueden reintentarse y deben tratarse como idempotentes.
