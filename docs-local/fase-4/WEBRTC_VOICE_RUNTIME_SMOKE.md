# Smoke real — WebRTC Voice Runtime

Este procedimiento valida el circuito real. No sustituir sus evidencias con mocks ni con una compilación exitosa.

## Precondiciones

- Migración `202609090001` aplicada en PostgreSQL y una sola head Alembic.
- Backend y `voice-runtime/` desplegados desde el mismo commit.
- LiveKit accesible por WSS desde el navegador y por el runtime.
- Agente Sandra activo con `published_version_id` y binding realtime Ultravox válido.
- Tenant canary con `agent_builder_v2=true` y `voice_runtime_v2=true`; demás tenants continúan deshabilitados.
- Usuario `tenant_admin` del tenant canary, navegador con micrófono y salida de audio.

Variables del backend: `VOICE_RUNTIME_SERVICE_SECRET`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME` y opcionalmente `VOICE_WEBRTC_TOKEN_TTL_SECONDS`.

Variables del runtime: `CONTROL_PLANE_BASE_URL`, `VOICE_RUNTIME_SERVICE_SECRET`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_AGENT_NAME`, `ULTRAVOX_API_KEY` y opcionalmente `VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS`.

No copiar valores de estas variables al reporte, screenshots o logs.

## Prueba

1. Abrir `/es/voice-ai/agents/{agent_id}` y confirmar que el agente está activo/publicado.
2. Pulsar **Probar agente** y permitir micrófono.
3. Confirmar que la UI pasa por Preparando, Agente iniciando, Conectando y Escuchando.
4. Decir exactamente: **“Hola Sandra, ¿me escuchas?”**
5. Escuchar una respuesta completa del agente en el mismo navegador.
6. Pulsar **Finalizar prueba** y confirmar micrófono inactivo/conexión desconectada.

## Evidencia esperada

Una sola `VoiceSession`, una sola Room `sg-vs-{session_id}` y un dispatch. Estados:

```text
requested -> dispatching -> dispatched -> starting -> connected -> ending -> ended
```

Eventos mínimos, en orden causal:

```text
voice.session.requested
voice.session.dispatched
voice.session.started
voice.agent.ready
voice.participant.connected
voice.audio.input.started
voice.transcript.final
voice.session.connected
voice.audio.output.started
voice.audio.output.completed
voice.participant.disconnected
voice.session.ended
```

La evidencia de audio E2E requiere conjuntamente: transcript final de la frase, respuesta audible en navegador y finalización limpia. `voice.audio.output.started` por sí solo no prueba playback del navegador.

## Logs seguros a revisar

Se permiten `tenant_id`, `voice_session_id`, `agent_id`, `agent_version_id`, `livekit_room_name`, `livekit_job_id`, `livekit_dispatch_id`, `runtime_engine`, `provider`, `channel`, event type y error code sanitizado. No registrar token participante, JWT, API keys, secretos, prompt completo, audio ni PII.

## Diagnóstico

- 403 al crear sesión/token: confirmar `voice_runtime_v2` sólo en el tenant canary y rol de escritura.
- 409 al pedir token: revisar estado terminal, `runtime_engine`, `livekit_room_name` y configuración LiveKit del backend.
- Dispatch failed: validar URL/credenciales LiveKit en el contenedor backend y que la imagen incluya `livekit-api==1.2.1`.
- `participant_join_timeout`: comprobar WSS público, token room-scoped, firewall/TURN y permiso del micrófono.
- Participante sin transcript: comprobar publicación `microphone`, suscripción del AgentSession y sesión Ultravox.
- Transcript sin audio: comprobar track remoto, autoplay (`Activar audio`), dispositivo de salida y eventos output.
- Sesión zombie: revisar participant disconnected, shutdown callback y timeout configurado.

## Registro del resultado

| Nivel | Estado actual | Evidencia requerida |
| --- | --- | --- |
| Local unit/integration mocked | Implementado; volver a ejecutar en cada commit | comandos y salida de suites |
| Staging LiveKit real | Pendiente | session/dispatch/participant |
| Staging Ultravox real | Pendiente | transcript final y output events |
| Staging audio bidireccional | Pendiente | frase reconocida y respuesta audible |
| Production canary | Pendiente; ejecutar sólo tras staging | una sesión controlada y logs sanitizados |

No marcar staging o producción como verificados sin fecha, commit, sesión técnica y evidencia audible observada por el operador.

## Siguiente sprint

SIP Participant Ingress debe reutilizar la misma `VoiceSession`, Room, `voice-runtime`, `AgentSession` y Ultravox. Este cambio no implementa Carrier, Asterisk ni LiveKit SIP.
