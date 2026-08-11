# Voice Experience Context Submissions — Etapa 2

Estado: implementado en `feature/voice-experience-context-submissions`.

## Alcance

La página pública `/{locale}/voice/{slug}` captura los ocho tipos de campo pre-call, consentimiento y verificación Turnstile. `POST /api/v1/public/voice-experiences/{slug}/submissions` no usa Auth0, bearer ni tenant headers. Devuelve un `context_token` efímero sólo en la respuesta y mantiene `calls: false`; WebRTC, micrófono, `joinUrl`, Ultravox y los endpoints legacy de llamadas siguen fuera de alcance.

## Persistencia e historial

La revisión `202608110001`, descendiente lineal de `202608050003`, crea:

- `tenant_voice_experience_submissions`: tenant con `ON DELETE CASCADE`; experiencia, versión exacta y schema histórico sin cascade; locale y evidencia de consentimiento coherente por constraint.
- `tenant_voice_experience_submission_values`: valores JSON tipados por clave/tipo de campo y borrado junto con la submission.
- `tenant_voice_context_sessions`: sólo `sha256(context_token)`, referencias históricas y expiración configurable; nunca guarda el token plaintext.
- `voice_public_rate_limit_windows`: contador PostgreSQL único por `(scope, window_start)` e índice de retención.

El schema se resuelve siempre desde `TenantVoiceExperienceVersion.context_schema_id`, nunca desde el draft actual de la experiencia. Bajo `SELECT FOR UPDATE`, la versión publicada actual debe coincidir con `request.version`; de lo contrario responde `409 experience_version_changed` sin persistir filas.

## Fronteras de sesión

1. A — pre-resolución en una sesión corta que se cierra antes de Cloudflare.
2. B — cada consumo global o tenant del rate limiter abre y confirma su propia sesión, por lo que la cuota sobrevive a `404`, `409`, `422` y rollback primario.
3. C — después de Turnstile, una única transacción primaria bloquea la experiencia, revalida snapshot/schema, valida campos/consentimiento e inserta submission, values y context session.

La proyección CRM ocurre después del commit primario en otra sesión. Sólo usa email válido o teléfono originalmente internacional con `+`; no infiere país para teléfonos locales. Registra evento sanitizado `success`, `skipped` o `failed`; sus errores no invalidan la respuesta aceptada.

## Seguridad pública

- El límite global por IP se consume antes de leer o validar JSON. Después del pre-resolve se consume tenant+IP.
- La IP se normaliza y pseudonimiza con HMAC-SHA256 y `VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET`. `CF-Connecting-IP` sólo se confía con `TRUST_CLOUDFLARE_CONNECTING_IP=true`; nunca se acepta `X-Forwarded-For` arbitrario.
- Turnstile falla cerrado por token/secret ausente, timeout, error HTTP o `success != true`. El helper legacy de `/api/v1/calls` no se modificó.
- Pydantic valida manualmente el envelope con tipos estrictos y `extra="forbid"`; no devuelve `loc`, `msg` ni `input`.
- Los errores de campo se limitan a `required`, `unknown_field`, `invalid_type`, `too_long`, `too_short`, `invalid_option`, `invalid_format` y `consent_required`.
- Reglas históricas admitidas: `min_length`, `max_length`, `min`, `max`. Claves desconocidas se ignoran; una regla soportada corrupta falla cerrado con error genérico y log sin respuestas ni configuración completa.

## Turnstile en frontend

Producción exige `NEXT_PUBLIC_TURNSTILE_SITE_KEY`. Sin clave y fuera del modo de prueba, el submit permanece deshabilitado y no se fabrica token. Playwright habilita exclusivamente `NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE=1` desde su config. El token vive en memoria React; tras cualquier POST no exitoso o error de red se elimina y el widget se resetea/remonta antes de permitir otro intento.

## Configuración y despliegue

Backend:

```text
VOICE_CONTEXT_SESSION_TTL_SECONDS=600
VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_GLOBAL_IP_PER_MINUTE=20
VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_TENANT_IP_PER_MINUTE=5
VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET=<secreto largo por entorno>
TRUST_CLOUDFLARE_CONNECTING_IP=false
```

Frontend: configurar `NEXT_PUBLIC_TURNSTILE_SITE_KEY`. Antes de habilitar confianza Cloudflare, restringir el origin para que sólo Cloudflare pueda alcanzarlo. Aplicar la migración en PostgreSQL, confirmar una sola head, verificar el hard body-size limit del reverse proxy y ejecutar el roundtrip upgrade/downgrade/upgrade.
