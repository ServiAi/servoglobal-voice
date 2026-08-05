# Voice Experience Management

Estado: tercer incremento backend implementado en `feature/voice-experience-management`.

## Alcance

Este incremento agrega administración autenticada y tenant-scoped de Voice Experiences. No agrega frontend, builder, página o formulario público, tokens públicos, context submission, CRM call context, WebRTC, `joinUrl`, llamadas Ultravox, WhatsApp, dominios personalizados ni analítica.

Tampoco existen todavía endpoints públicos ni runtime WebRTC para consumir una experiencia publicada.

## Persistencia

- `tenant_voice_experiences` conserva el draft mutable, un slug opaco generado por el servidor, estado, configuración JSON tipada y la referencia opcional a la versión publicada actual.
- `tenant_voice_experience_versions` conserva snapshots inmutables. La combinación `(experience_id, version)` es única.
- `max_experiences` cuenta sólo experiencias no archivadas. Context schemas y sus versiones no consumen este límite.
- El slug es globalmente único, estable y no deriva del nombre, usuario o datos del tenant.

La revisión Alembic `202608050002` desciende directamente de `202608050001`. Crea primero la experiencia, después sus versiones y finalmente la FK circular `published_version_id`; el downgrade elimina esa FK antes de las tablas.

## Reglas de publicación

La experiencia, el agente y el schema se resuelven siempre dentro de `AuthContext.tenant.id`. El agente debe pertenecer al tenant; el schema debe pertenecer al mismo tenant y agente. Sólo un schema `active` permite publicar.

Cada publicación bloquea la fila de la experiencia, calcula la siguiente versión y persiste snapshot más cambio de estado en una sola transacción. El constraint único impide versiones duplicadas; las violaciones conocidas se reportan como conflicto y los `IntegrityError` desconocidos se relanzan.

Editar la experiencia no modifica snapshots anteriores. Despublicar conserva el historial. Una experiencia publicada debe despublicarse antes de archivarse y una experiencia archivada es inmutable.

## API privada

- `GET /api/v1/voice/experiences`
- `POST /api/v1/voice/experiences`
- `GET /api/v1/voice/experiences/{experience_id}`
- `PUT /api/v1/voice/experiences/{experience_id}`
- `POST /api/v1/voice/experiences/{experience_id}/publish`
- `POST /api/v1/voice/experiences/{experience_id}/unpublish`
- `POST /api/v1/voice/experiences/{experience_id}/archive`
- `GET /api/v1/voice/experiences/{experience_id}/versions`

Lectura: `platform_admin` interno en su contexto actual, `tenant_admin`, `tenant_analyst` y `tenant_viewer`. Escritura: `platform_admin` interno en su contexto actual y `tenant_admin`. Un `platform_admin` no interno recibe `403`.

Los modelos Pydantic usan `extra="forbid"` en el body y en `content`, `theme`, `consent` y `call_settings`. Las URLs configurables exigen HTTPS y el color primario exige formato hexadecimal de seis dígitos. Las respuestas no incluyen tenant, actor, system prompt, tools, secretos de proveedor, credenciales SIP ni PII interna.
