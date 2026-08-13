# Voice Experience WebRTC Runtime — Etapa 3

Estado: implementado en `feature/voice-experience-webrtc-runtime`.

## Contrato y one-shot

`POST /api/v1/public/voice-experiences/{slug}/calls` acepta únicamente `{ "context_token": "..." }`, sin Auth0, tenant, agente, prompt, tools ni respuestas del navegador. El body se valida manualmente después del rate limit global y todas las respuestas usan `Cache-Control: no-store`. El éxito devuelve un `join_url` efímero y capacidades `submissions=true/calls=true`.

El servidor resuelve el hash del token y busca primero `TenantVoiceRuntimeCall`. Si existe, entra a recovery y nunca crea una segunda llamada. En first launch, PRECHECK valida admisión y configuración tenant; TX-A revalida sesión, expiración, publicación, versión, coherencia y feature, crea el claim `ON CONFLICT`, consume la context session y crea `CrmVoiceCall` en una sola transacción.

Estados: `reserved → starting → ready → connected → ended`; `failed` es terminal y `unknown` conserva intentos ambiguos. Un `reserved` vencido sólo ejecuta provider I/O si gana el CAS de takeover. Un `starting` vencido pasa a `unknown` y nunca repite Create Call.

## Proveedor y recovery

Ultravox usa exclusivamente `TenantVoiceProviderConfig` y el `provider_agent_id` vivo de `TenantVoiceAgentConfig`. El request envía metadata string (`voice_call_id`, `runtime_call_id`, `source`) y `templateContext.user_context` con valores tipados y locale. No aplica overrides de prompt, tools o language. El agente remoto debe declarar y consumir ese namespace.

Un `2xx` parcial, timeout de lectura, escritura ambigua o `5xx` produce `unknown`. Con `provider_call_id`, recovery consulta esa misma llamada; sin ID, lista por `metadata.runtime_call_id`, agente esperado y fecha cercana. Cero resultados conserva `unknown`; más de uno falla cerrado para reconciliación manual. Nunca se repite Create Call.

## Webhook, analytics y CRM

La rama runtime de `POST /api/v1/voice/webhook/ultravox` resuelve `metadata.voice_call_id` no confiable hacia `CrmVoiceCall → TenantVoiceRuntimeCall → tenant_id` confiable. Verifica provider y firma HMAC tenant fail-closed; no acepta tenant desde metadata.

Cada evento usa `dedup_key=ultravox:{provider_call_id}:{event_type}`. Claim, `analytics.Call`, `CallEvent`, `CrmVoiceCall`, CAS runtime y `CrmVoiceCallEvent` se confirman juntos; un error revierte también el claim. `call.billed` alimenta `TenantUsageService`. Las activities CRM ocurren después del core commit, con dedup y sólo cuando existe contacto; CRM nullable nunca bloquea lifecycle, analytics o billing.

## Frontend y seguridad

Después de la submission, la UI muestra el CTA; `auto_start` es sólo una pista de UI y jamás hace POST. Un gesto explícito ejecuta `getUserMedia({audio:true})`, detiene todos los tracks del preflight y sólo entonces lanza la llamada. El adapter real usa `UltravoxSession`; Playwright usa un fake únicamente con `NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE=1`. Hangup y unmount desconectan la sesión.

Token y `join_url` viven sólo en memoria React: no DB, logs, CRM, analytics, cookies, storage, URL ni DOM visible. `call_settings.language` es hint de UI/runtime, no override del proveedor. Los campos sensibles pre-call pueden viajar bajo `user_context`, pero nunca se registran. El riesgo residual de prompt injection queda limitado a ese namespace de datos no confiables.

## Despliegue

Cada tenant necesita provider activo, API key y webhook secret cifrados, agente remoto compatible con `user_context`, y webhook para `call.started`, `call.joined`, `call.ended` y `call.billed`. Antes de confiar `CF-Connecting-IP`, el origin debe aceptar tráfico sólo del proxy confiable. La migración `202608120001_voice_experience_runtime_calls` crea el runtime durable y los uniques de dedup.
