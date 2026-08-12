# Voice Experience Context Submissions — Etapa 2

Estado: implementado en `feature/voice-experience-context-submissions`.

## Alcance

La página pública `/{locale}/voice/{slug}` captura los ocho tipos de campo pre-call, consentimiento y verificación Turnstile. `POST /api/v1/public/voice-experiences/{slug}/submissions` no usa Auth0, bearer ni tenant headers. Devuelve un `context_token` efímero sólo en la respuesta y mantiene `calls: false`; WebRTC, micrófono, `joinUrl`, Ultravox y los endpoints legacy de llamadas siguen fuera de alcance.

## Persistencia e historial

La revisión `202608110001`, descendiente lineal de `202608050003`, crea:

- `tenant_voice_experience_submissions`: tenant con `ON DELETE CASCADE`; experiencia, número/ID de versión exacta, schema histórico, locale `es|en`, evidencia de consentimiento y referencias CRM opcionales con `ON DELETE SET NULL`.
- `tenant_voice_experience_submission_values`: tenant, fecha y valores JSON no nulos por clave/tipo de campo, únicos por `(submission_id, field_key)` y borrados junto con la submission.
- `tenant_voice_context_sessions`: relación 1:1 con submission, sólo `sha256(context_token)`, referencias históricas, expiración y lifecycle `active`, `consumed`, `expired`; nunca guarda el token plaintext. El consumo futuro usa una actualización condicional atómica y no expone endpoint público en Etapa 2.
- `voice_public_rate_limit_windows`: contador PostgreSQL único por `(scope, window_start)` e índice de retención.

El schema se resuelve siempre desde `TenantVoiceExperienceVersion.context_schema_id`, nunca desde el draft actual de la experiencia. Bajo `SELECT FOR UPDATE`, la versión publicada actual debe coincidir con `request.version`; de lo contrario responde `409 experience_version_changed` sin persistir filas.

## Fronteras de sesión

1. A — pre-resolución en una sesión corta que se cierra antes de Cloudflare.
2. B — cada consumo global o tenant del rate limiter abre y confirma su propia sesión, por lo que la cuota sobrevive a `404`, `409`, `422` y rollback primario.
3. C — después de Turnstile, una única transacción primaria bloquea la experiencia, revalida snapshot/schema, valida campos/consentimiento e inserta submission, values y context session.

La proyección CRM ocurre después del commit primario en otra sesión: resuelve el primer campo de tipo `email` y el primer `phone` originalmente internacional con `+`, crea/resuelve contacto y lead con `context_id=submission.id` y `source=voice_experience`, registra activity `voice_experience_submitted` y persiste `crm_contact_id`/`crm_lead_id`. `full_name` y `company` sólo se leen por clave exacta. El evento `success`, `skipped` o `failed` contiene únicamente `experience_id` y `version`; un rollback CRM no invalida la submission ni el HTTP 200.

## Seguridad pública

- El límite global por IP se consume antes de leer o validar JSON. Después del pre-resolve se consume tenant+IP.
- La IP se normaliza y pseudonimiza con HMAC-SHA256 y `VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET`. `CF-Connecting-IP` sólo se confía con `TRUST_CLOUDFLARE_CONNECTING_IP=true`; nunca se acepta `X-Forwarded-For` arbitrario.
- Turnstile falla cerrado por token/secret ausente, timeout, error HTTP o `success != true`. El helper legacy de `/api/v1/calls` no se modificó.
- Pydantic valida el envelope con tipos estrictos y `extra="forbid"`: `hp` 200, token 2048, hasta 100 answers, claves de 80 y tamaño lógico agregado de aproximadamente 50 KB. El hard body limit permanece en el proxy.
- Límites globales: text 200, textarea 5000, email 254, phone 32, enteros ±1.000.000.000 y fechas reales entre 1900 y 2100. `validation_json` sólo puede restringirlos; select exige membresía exacta y checkbox exige booleano.
- Los errores de campo se limitan a `required`, `unknown_field`, `invalid_type`, `too_long`, `too_short`, `invalid_option`, `invalid_format` y `consent_required`.
- Reglas históricas admitidas: `min_length`, `max_length`, `min`, `max`. Claves desconocidas se ignoran; una regla soportada corrupta falla cerrado con `500 internal_error` y log limitado a `error_type`.
- Fallos inesperados de DB/config/programación responden `500 internal_error`; `429` se reserva exclusivamente para una cuota realmente excedida. Token Turnstile ausente, vacío, inválido o con timeout responde `422 verification_failed`.

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

El POST usa siempre el locale real de la URL (`es` o `en`), aun cuando `default_locale` del snapshot sea distinto.
