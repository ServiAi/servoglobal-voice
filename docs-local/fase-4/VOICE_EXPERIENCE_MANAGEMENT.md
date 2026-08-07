# Voice Experience Management

Estado: tercer incremento backend implementado en `feature/voice-experience-management`.

## Alcance

Este incremento agrega administración autenticada y tenant-scoped de Voice Experiences. No agrega frontend, builder, página o formulario público, tokens públicos, context submission, CRM call context, WebRTC, `joinUrl`, llamadas Ultravox, WhatsApp, dominios personalizados ni analítica.

La administración descrita aquí continúa siendo privada. El incremento posterior `feature/voice-experience-public-runtime` agregó una lectura pública sanitizada del snapshot publicado, pero no captura de datos ni runtime WebRTC; ver `VOICE_EXPERIENCE_PUBLIC_RUNTIME.md`.

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
- `DELETE /api/v1/voice/experiences/{experience_id}`
- `GET /api/v1/voice/experiences/{experience_id}/versions`

Actualización (Etapa 0, `fix/voice-experience-functional-alignment`): `get_current_published_version()` resuelve estrictamente por `published_version_id` (fail-closed). `PUT` rechaza cambiar el agente si hay historial y `DELETE` sólo aplica a archivadas sin historial. Actualización posterior: el snapshot exacto puede representarse en la página pública de solo lectura, sin conectarlo a `/api/v1/calls`. Ver `VOICE_EXPERIENCE_FUNCTIONAL_ALIGNMENT.md` y `VOICE_EXPERIENCE_PUBLIC_RUNTIME.md`.

Lectura: `platform_admin` interno en su contexto actual, `tenant_admin`, `tenant_analyst` y `tenant_viewer`. Escritura: `platform_admin` interno en su contexto actual y `tenant_admin`. Un `platform_admin` no interno recibe `403`.

Los modelos Pydantic usan `extra="forbid"` en el body y en `content`, `theme`, `consent` y `call_settings`. Las URLs configurables exigen HTTPS y el color primario exige formato hexadecimal de seis dígitos. Las respuestas no incluyen tenant, actor, system prompt, tools, secretos de proveedor, credenciales SIP ni PII interna.
