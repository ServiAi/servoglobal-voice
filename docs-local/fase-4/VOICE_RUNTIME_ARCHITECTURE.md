# ServiGlobal Voice Runtime — arquitectura Sprints 1–5

## Control Plane y Data Plane

```text
TenantAgent -> TenantAgentVersion -> VoiceSession
                                      |
                                      v
AgentCompilerService -> RuntimeSessionSpecV1 -> LiveKit explicit dispatch
                                                   |
                                                   v
                                    ServiGlobal Voice Runtime
                                                   |
                         Ultravox RealtimeModel -> AgentSession -> Room
```

ServiGlobal conserva la autoridad sobre tenant, agente, versión, estado, auditoría y configuración. LiveKit sólo transporta audio, rooms y jobs. Ultravox ejecuta speech-to-speech. El deploy `voice-runtime/` no importa modelos/servicios del backend ni conoce `DATABASE_URL`.

`VoiceSession` fija el `agent_version_id` publicado antes del dispatch y aplica un lifecycle explícito. `VoiceSessionEvent` es append-only y deduplica `event_id`. El contrato V1 conserva `runtime.realtime.settings` para configuración segura como voz y temperatura. Cuando una versión usa el vínculo legacy, el Control Plane compila únicamente la voz no secreta; ninguna credencial entra al spec.

Los endpoints `/api/v1/internal/voice-runtime/sessions/{id}/spec|events` aceptan sólo JWT HMAC HS256 de corta duración con `iss`, `aud`, `sub`, `iat` y `exp`. El secreto se entrega por entorno y no se registra. Usuarios Auth0 normales no atraviesan esta dependencia.

El Control Plane crea un dispatch explícito con agente estable `serviglobal-voice-runtime`, room `sg-vs-{session_id}` y metadata JSON que contiene sólo `session_id`. El worker valida esa forma exacta, recupera el spec, comprueba el ID, resuelve el provider y falla cerrado ante metadata, contrato, auth o provider inválidos.

`UltravoxLiveKitRuntime` usa el plugin oficial. Mapea prompt publicado, modelo, voz, idioma base (`es-CO` a `es`), temperatura 0–1 y primer hablante. El turn detection permanece server-side porque el plugin no permite desactivarlo. La interrupción `conservative` desactiva interrupciones; los otros modos usan el soporte disponible de LiveKit. El saludo se incorpora una sola vez al prompt automático para evitar doble reproducción.

El Dockerfile usa Python 3.11, usuario no root y el health/readiness nativo de `AgentServer` en `/` puerto `8081`. Variables requeridas: `CONTROL_PLANE_BASE_URL`, `VOICE_RUNTIME_SERVICE_SECRET`, `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` y `ULTRAVOX_API_KEY`. Dependencias fijadas: `livekit-agents==1.7.1`, `livekit-plugins-ultravox==1.7.1`; backend: `livekit-api==1.2.1`.

El camino está detrás de `voice_runtime_v2`, deshabilitado por defecto. No se modifican VoiceClient, callbacks, webhooks, Asterisk, SIP ni `TenantVoiceAgentConfig`. Sin credenciales no se puede afirmar smoke real de LiveKit/Ultravox. WebRTC browser, SIP, herramientas, BYOK, handoff y otros providers quedan para fases posteriores.
