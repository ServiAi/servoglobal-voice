# Voice Experience Public Runtime — lectura inicial

Estado: lectura inicial implementada en `feature/voice-experience-public-runtime`; context submissions agregadas después en `feature/voice-experience-context-submissions`.

## Alcance

Este incremento publica una representación de solo lectura de una Voice Experience preparada:

- Backend público: `GET /api/v1/public/voice-experiences/{slug}`.
- Frontend público bilingüe: `/{locale}/voice/{slug}`.
- Campos visibles ordenados y consentimiento del snapshot publicado.
- Diseño responsive, enlaces HTTPS validados y formulario público habilitado por Etapa 2.

Etapa 2 agregó context submissions, consentimiento persistido, context sessions y correlación CRM contact/lead/activity. Siguen fuera de alcance micrófono, WebRTC, `joinUrl`, Ultravox, callbacks e integración con `/api/v1/calls`.

| Capacidad | Estado |
| --- | --- |
| Public runtime de lectura | ✅ |
| Submissions | ✅ Ver `VOICE_EXPERIENCE_CONTEXT_SUBMISSIONS.md` |
| Context session | ✅ Etapa 2: `active` → `consumed` o `expired` |
| WebRTC | ❌ |
| Calls | ❌ |

## Resolución fail-closed

El slug debe cumplir `^[A-Za-z0-9_-]{1,64}$`. Para responder, la experiencia debe existir por slug global, estar `published`, tener `published_version_id`, conservar habilitada la feature `voice_experiences` y referenciar exactamente una versión de la misma experiencia y tenant. El schema se toma de `version.context_schema_id`, no del draft actual, y también debe pertenecer al tenant.

Se incluyen sólo campos con `ask_if_missing`, `prefill_and_confirm` o `trust_prefill`, ordenados por posición. Los modos internos y durante llamada se filtran en el servidor. Un slug desconocido, estado no publicado, feature deshabilitada o referencia inconsistente produce el mismo `404` genérico. Las respuestas públicas llevan `Cache-Control: no-store`.

## Contrato público

El DTO incluye únicamente slug, locale, número de versión, contenido visible, theme, consentimiento, campos visibles y capacidades `submissions: true` / `calls: false`. No expone IDs internos, tenant, agente/proveedor, prompt, tools, credenciales, SIP, sensibilidad, `collection_mode` ni `validation_json`.

La página Next.js es dinámica (`force-dynamic`), consulta sin bearer token con `cache: no-store`, declara `noindex` y usa una página 404 genérica. Etapa 2 habilita inputs, consentimiento y submission con Turnstile; el locale persistido proviene de `/{locale}/voice/{slug}`, no del locale por defecto del snapshot. Las llamadas continúan deshabilitadas.

## Cobertura

- `backend/test_public_voice_experiences.py`: publicación exacta, sanitización, estados indistinguibles, feature, referencias inconsistentes, snapshots y schemas históricos, filtrado y no-store.
- `frontend/tests/public-voice-experiences.spec.ts`: ruta pública real con backend local, responsive, controles deshabilitados, URLs inseguras, accesibilidad acotada al runtime, ausencia de Auth0 y paridad de traducciones.

La lectura original no requirió migración. La captura posterior usa `202608110001`; ver `VOICE_EXPERIENCE_CONTEXT_SUBMISSIONS.md`.
