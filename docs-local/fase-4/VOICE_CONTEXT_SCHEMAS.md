# Voice Context Experiences — Incremento 2

## Alcance

Este incremento agrega configuración privada, versionada y tenant-scoped de esquemas de contexto para agentes de voz. No conecta todavía los esquemas al runtime de llamadas y no incluye frontend, formularios públicos, WebRTC, WhatsApp ni analítica.

## Persistencia

- `tenant_voice_context_schemas`: identifica cada experiencia por `(agent_config_id, schema_key)` y conserva versiones `draft`, `active` y `archived`.
- `tenant_voice_context_fields`: define campos ordenados con tipo, modo de recolección, sensibilidad, validación y opciones.
- Migración: `202608050001_voice_context_schemas`, descendiente directa de `202608040001`.

Los schemas activos o archivados son inmutables. `new-version` clona metadata y campos a un draft con `version + 1`. Activar una versión archiva, en la misma transacción, la versión activa anterior del mismo lineage.

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

Lectura: `platform_admin` interno, `tenant_admin`, `tenant_analyst`, `tenant_viewer`. Escritura: `platform_admin` interno y `tenant_admin`.

Los cuerpos usan `extra="forbid"`: no aceptan `tenant_id`, `agent_config_id` ni campos arbitrarios. Las respuestas no exponen `tenant_id`, `created_by_user_id`, prompts, tools, credenciales ni secretos del agente.

## Límites y transiciones

- `max_experiences` cuenta lineages con al menos una versión draft o active en todo el tenant.
- `max_context_fields` limita los campos de cada schema.
- Transiciones: `draft -> active -> archived` y `draft -> archived`.
- Un schema active o archived sólo puede evolucionar mediante `new-version`.

## Eventos

Se registran eventos sanitizados `context_schema_created`, `context_schema_activated` y `context_schema_archived` sobre el recurso `voice_context_schema`.

## Fuera de alcance

Consumo del schema durante llamadas, builder/UI, endpoints o formularios públicos, WebRTC, `joinUrl`, WhatsApp, analítica y borrado físico de schemas.
