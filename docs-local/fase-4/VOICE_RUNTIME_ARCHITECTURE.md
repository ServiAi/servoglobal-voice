# ServiGlobal Voice Runtime — arquitectura Sprints 1–6

## Flujo canónico

```text
Agent Builder -> VoiceSession -> AgentCompilerService -> RuntimeSessionSpecV1
                       |                                  |
                       v                                  v
              LiveKit explicit dispatch          voice-runtime
                       |                                  |
                       +---------- LiveKit Room ----------+
                                      |
                             Browser WebRTC participant
                                      |
                           microphone <-> agent audio
                                      |
                         Ultravox RealtimeModel/AgentSession
```

ServiGlobal sigue siendo el Control Plane y fuente de verdad de tenant, agente, versión, estado y auditoría. LiveKit es la capa realtime y Ultravox es el primer modelo. El navegador sólo habla con LiveKit; no recibe credenciales Ultravox ni conecta directamente con ese proveedor. El runtime independiente no usa la base de datos.

## Creación y acceso del participante

`POST /api/v1/voice/sessions` crea una sesión `channel=webrtc`, fija el `agent_version_id` publicado y despacha el agente a `sg-vs-{session_id}`. El endpoint autenticado `POST /api/v1/voice/sessions/{session_id}/webrtc-token` deriva el tenant desde `AuthContext`, carga la sesión con ese tenant y usa exclusivamente `session.livekit_room_name`.

El token expira en 300 segundos por defecto (`VOICE_WEBRTC_TOKEN_TTL_SECONDS`, acotado entre 30 y 600), usa identity opaca `web-{uuid}` y concede sólo `roomJoin`, `canSubscribe`, `canPublish` y `canPublishSources=[microphone]`. Niega data, cámara, screen share, administración, creación, grabación, ingress y actualización de metadata. Nunca se devuelve `LIVEKIT_API_SECRET`.

El frontend usa `livekit-client==2.21.0`. `LiveKitVoiceRuntimeAdapter` conecta con `server_url` y el participant token, publica un único micrófono mediante `setMicrophoneEnabled(true)`, adjunta tracks de audio remotos y ofrece reanudación explícita si el navegador bloquea autoplay. Al finalizar deshabilita micrófono, desconecta la Room, detach/remove de audio y elimina listeners. Los adapters legacy Fake/Ultravox se conservan.

## Lifecycle y eventos

La máquina principal permanece simple:

```text
requested -> dispatching -> dispatched -> starting -> connected -> ending -> ended
                                                   \-> failed/cancelled
```

`AgentSession.start()` ya no significa conversación conectada. El runtime emite:

```text
voice.session.started
voice.agent.ready
voice.participant.connected
voice.audio.input.started
voice.transcript.final
voice.session.connected
voice.audio.output.started
voice.audio.output.completed
voice.participant.disconnected
voice.session.ended | voice.session.failed
```

`voice.session.connected` se emite una sola vez después del primer transcript final del usuario, señal de que Browser -> LiveKit -> AgentSession -> Ultravox recibió audio. Los eventos detallados permanecen en `VoiceSessionEvent`; sólo started/connected/ended/failed cambian el estado principal.

El runtime ignora participantes con kind `PARTICIPANT_KIND_AGENT`. Si no entra un participante humano en `VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS` (60 por defecto), emite `participant_join_timeout`, cierra `AgentSession` y el modelo, y solicita shutdown del job. Cuando el humano sale, emite disconnected/ended y ejecuta el mismo cleanup idempotente.

## Seguridad y compatibilidad

Los endpoints internos spec/events siguen protegidos por JWT HMAC corto. El dispatch contiene únicamente `session_id`; `RuntimeSessionSpecV1` rechaza claves con forma de secreto. No se loguean JWT, participant tokens, API keys, prompts completos ni payloads completos. `voice_runtime_v2` continúa deshabilitado por defecto y debe habilitarse sólo para el tenant canary. VoiceClient, Ultravox web legacy, Asterisk, SIP, webhooks y `TenantVoiceAgentConfig` no se eliminan ni se rediseñan.

## Estado de verificación

- Implementado: backend, runtime, frontend, CI y documentación.
- Unit/integration con mocks: cubierto por suites backend, runtime y adapter.
- LiveKit real: pendiente de smoke en staging.
- Ultravox real: pendiente de smoke en staging.
- Audio bidireccional real: pendiente de smoke en staging.
- Producción: pendiente; no verificada.
