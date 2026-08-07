# Voice Context Experiences — Incremento 2

## Alcance

Este incremento agrega configuración privada, versionada y tenant-scoped de esquemas de contexto para agentes de voz. No conecta todavía los esquemas al runtime de llamadas y no incluye frontend, formularios públicos, WebRTC, WhatsApp ni analítica.

## Persistencia

- `tenant_voice_context_schemas`: identifica cada schema lineage por `(agent_config_id, schema_key)` y conserva versiones `draft`, `active` y `archived`.
- `tenant_voice_context_fields`: define campos con posición única, descripción, tipo, modo de recolección, sensibilidad, validación y opciones tipadas.
- Migración: `202608050001_voice_context_schemas`, descendiente directa de `202608040001`.

Los schemas activos o archivados son inmutables. `new-version` clona metadata y campos a un draft con `version + 1`. Cada lineage admite como máximo una versión active y una draft; la base de datos lo protege con índices únicos parciales.

## API privada tenant

Todas las rutas requieren `voice_experiences`, derivan `tenant_id` de `AuthContext` y revalidan que el agente pertenezca al tenant.

| Método | Ruta |
| --- | --- |
| `GET` / `POST` | `/api/v1/voice/agents/{agent_config_id}/context-schemas` |
| `GET` | `/api/v1/voice/agents/{agent_config_id}/context-schemas/{schema_key}/versions` |
| `GET` / `PUT` | `/api/v1/voice/context-schemas/{schema_id}` |
| `POST` | `/api/v1/voice/context-schemas/{schema_id}/fields` |
| `PUT` / `DELETE` | `/api/v1/voice/context-schemas/{schema_id}/fields/{field_id}` |
| `POST` | `/api/v1/voice/context-schemas/{schema_id}/activate` |
| `POST` | `/api/v1/voice/context-schemas/{schema_id}/archive` |
| `POST` | `/api/v1/voice/context-schemas/{schema_id}/new-version` |
| `DELETE` | `/api/v1/voice/context-schemas/{schema_id}` |

Lectura: `platform_admin` interno, `tenant_admin`, `tenant_analyst`, `tenant_viewer`. Escritura: `platform_admin` interno y `tenant_admin`.

Los cuerpos usan `extra="forbid"`: no aceptan `tenant_id`, `agent_config_id` ni campos arbitrarios. Las respuestas no exponen `tenant_id`, `created_by_user_id`, prompts, tools, credenciales ni secretos del agente.

## Límites y transiciones

- `max_context_fields` limita los campos de cada schema.
- `max_experiences` ya se aplica sobre `TenantVoiceExperience` (ver `VOICE_EXPERIENCE_MANAGEMENT.md`): cuenta experiencias no archivadas, no context schemas ni sus versiones.
- Los campos `select` exigen opciones tipadas con values únicos; los demás tipos no admiten opciones.
- Transiciones: `draft -> active -> archived` y `draft -> archived`.
- Un schema active o archived sólo puede evolucionar mediante `new-version`.
- El borrado físico solo se permite para un schema `archived` sin referencias tenant-scoped en `TenantVoiceExperience` ni `TenantVoiceExperienceVersion`. Una referencia actual o histórica responde `409` y no modifica ninguna fila.
- Eliminar un context schema nunca elimina una Voice Experience ni publication history. Un schema referenciado por un snapshot se conserva como parte del contrato reproducible de esa publicación.

## Eventos

Se registran eventos sanitizados `context_schema_created`, `context_schema_activated` y `context_schema_archived` sobre el recurso `voice_context_schema`.

## Fuera de alcance

Consumo del schema durante llamadas, formularios públicos, WebRTC, `joinUrl`, WhatsApp, analítica y una política completa de retención. La retención puede evolucionar posteriormente, pero el historial existente se conserva.
