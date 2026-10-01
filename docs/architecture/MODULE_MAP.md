# Mapa de módulos (bounded contexts)

Fuente: análisis AST de todos los imports de `backend/app/` (231 módulos Python, incluidos imports locales dentro de funciones) sobre `develop@f52e82f`, 2026-09-30. El código prevalece sobre la documentación previa.

## Diagnóstico

El backend es un **monolito por capas** (`api/endpoints`, `services`, `models`, `schemas`, `domain`, `core`, `workers`) que ya contiene bounded contexts reconocibles por nombre de archivo, pero sin fronteras: cualquier servicio importa cualquier servicio o modelo.

- `services/` tiene 127 archivos de 13 dominios distintos.
- `models/integrations.py` concentra 34 tablas de **seis** dominios (scheduling, WhatsApp, email, formularios, voz legacy, SIP, Chatwoot). Es la principal fuente de acoplamiento accidental: importar una tabla de scheduling arrastra el archivo de WhatsApp.
- A nivel de módulo Python sólo existían dos ciclos de import reales, ambos resueltos con imports perezosos: `agent_service ↔ ultravox_admin_service` y `custom_http_tool_executor ↔ tool_dispatch_service` (este último eliminado en esta iteración).
- A nivel de dominio hay **muchos ciclos** (ver `MODULE_DEPENDENCIES.md`). La mayoría se deben a modelos compartidos y a servicios orquestadores cross-domain, no a errores de diseño puntuales.
- `app/domain/` no es una capa de dominio común: contiene catálogos y contratos de tools, voice registry y notificaciones.

## Módulos identificados

Los límites se derivaron del código; donde el código contradice la propuesta inicial se indica.

| # | Módulo | Responsabilidad | Archivos principales hoy | Estado |
| --- | --- | --- | --- | --- |
| 1 | **Identity / Tenancy** | Tenant, User, Membership, Auth0, roles, `AuthContext`, feature flags (`TenantFeatureService`), onboarding, bootstrap. | `models/identity.py`, `models/tenant_features.py`, `api/auth/deps.py`, `services/{identity,auth0*,onboarding,bootstrap,tenant_feature}_service.py`, `api/endpoints/{me,auth0,admin/*}.py` | Legacy + `modules/identity/public.py` (sólo `FeatureFlags`). `api.auth.deps` sigue siendo de facto shared kernel. |
| 2 | **Agent Builder** | `TenantAgent`/`TenantAgentVersion`, drafts, publish, `AgentCompilerService`, identidad/instrucciones/comportamiento, configuración realtime y de voz provider-agnostic, `voice_registry`, `VoiceSelectionService`. | `models/agents.py`, `services/{agent,agent_compiler,voice_selection}_service.py`, `domain/voice_registry.py`, `api/endpoints/{agents,voice_registry}.py` | Legacy + `modules/agents/public.py` (facade mínima). |
| 3 | **Voice Orchestration** | `VoiceSession`/`VoiceSessionEvent`, `SessionContextV1`, `RuntimeSessionSpecV1`, lifecycle, dispatch, credenciales del runtime, `ContactResolutionService`, `VoiceCallProjectionService`, endpoints internos del runtime. | `models/voice_sessions.py`, `schemas/{session_context,runtime_session,voice_sessions}.py`, `services/{voice_session,voice_runtime_dispatcher,livekit_runtime_backend,voice_call_projection,contact_resolution,voice_runtime_webhook}_service.py`, `api/endpoints/{voice,voice_runtime}.py`, `security/voice_runtime_auth.py` | Legacy + `modules/voice/public.py`. |
| 4 | **Telephony** | SIP, LiveKit SIP, rutas SIP tenant, PBX/Asterisk, normalización de teléfonos, capacidad, outbound calling, callbacks. | `services/{livekit_sip,voice_sip_route,voice_session_sip,voice_capacity,voice_phone,outbound_voice_call,asterisk_provisioning,voice_callback}_service.py`, `workers/{asterisk_provisioner,voice_callback_worker}.py` | Legacy. |
| 5 | **Tool Platform** | Registry de tools de plataforma, schema/namespace, `ResolvedToolDefinition`, resolver plataforma+custom, contrato de tres orígenes (LLM/contexto/config), dispatch, Custom HTTP Tools, credenciales cifradas, SSRF-safe HTTP. | `app/modules/tools/**` | **Migrado** (primer vertical slice) y con frontera de datos endurecida: sólo DTOs de otros módulos. Patrón de referencia. |
| 6 | **CRM** | Contactos, leads, actividades, tareas, pipeline, transiciones, métricas, call context, bookings CRM (fila `CrmBooking`), mensajes WhatsApp CRM (fila), `CrmVoiceCall`. | `models/crm.py`, `services/crm_*_service.py`, `call_summary_service.py`, `api/endpoints/{crm,crm_voice,crm_whatsapp}.py` | Legacy + `modules/crm/public.py`. |
| 7 | **Scheduling** | Disponibilidad, booking (`BookingService`), Cal.com, Google Calendar, recursos, equipos, configuración. | `services/{booking*,calcom*,google_*,scheduling_*,date_resolution}_service.py`, tablas `tenant_scheduling_*`/`tenant_booking_configs`/`tenant_google_*` en `models/integrations.py`, `api/endpoints/{calcom,scheduling,voice_booking_tools}.py` | Legacy + `modules/scheduling/public.py`. |
| 8 | **Notifications** | Domain events, reglas, destinatarios, entregas, claims con lease, reintentos, recuperación, orquestador, worker. | `models/notifications.py`, `domain/{events,notification_*}.py`, `services/notification_*`, `domain_event_service.py`, `whatsapp_notification_executor.py`, `workers/notification_worker.py` | Legacy. |
| 9 | **Integrations / Messaging** | WhatsApp (config, plantillas, mensajes, Flows), Email (Resend, templates, assets, envíos), Chatwoot, catálogo de integraciones, eventos de integración. | `services/{whatsapp_*,meta_client,email_*,resend,chatwoot_*,integration}_service.py`, `api/endpoints/{integrations,whatsapp_*,chatwoot_webhook,email_assets}.py` | Legacy + `modules/integrations/public.py` (sólo WhatsApp). |
| 10 | **Voice Experiences** | Experiencias públicas de voz, versiones, submissions, context schemas, formularios públicos, Turnstile, rate limit. | `models/{voice_experiences,voice_submissions,voice_context}.py`, `services/{public_voice_*,voice_experience*,voice_context,form,turnstile,voice_public_rate_limiter}_service.py` | Legacy. **No estaba en la propuesta inicial**: el código muestra un contexto propio con 17 archivos. |
| 11 | **Voice Legacy (Ultravox directo)** | Flujo Ultravox pre-LiveKit: `voice_service`, webhooks, ingestión, persistencia de llamadas, `TenantVoiceAgentConfig`, admin de proveedor. | `services/{ultravox_*,voice_service,voice_client,voice_webhook,voice_call,call_persistence,call_status_normalizer,voice_agent,voice_config,voice_provider_admin}*.py` | Legacy. **Separado a propósito**: mezclarlo con Voice Orchestration ocultaría qué es rollback y qué es la ruta V2. `voice_config_service` (credenciales de proveedor) debe migrar a Voice Orchestration. |
| 12 | **Billing / Analytics** | Planes, uso, alertas, pricing, `analytics.Call`, snapshots, dashboard. | `models/{billing,analytics}.py`, `services/{tenant_usage,dashboard_analytics}_service.py`, `api/endpoints/dashboard.py` | Legacy. |
| — | **Shared kernel** | `db.base`, `db.session`, `db.url`, `db.mixins` (nuevo), `core.config`, `api.auth.deps`; de facto también `integration_event_service` (auditoría) y `secret_manager_service` (cifrado). | `app/db/`, `app/core/config.py` | Mantener pequeño; no mover lógica de negocio aquí. |

### Decisiones de agrupación tomadas del código

- **Voice** se divide en tres contextos (Orchestration, Experiences, Legacy) y Telephony aparte. Un único módulo `voice` tendría ~70 archivos y ocultaría el plan de retiro del flujo Ultravox directo.
- **Messaging vs Integrations**: WhatsApp y Email son canales con lógica de negocio propia (plantillas, Flows, composer), no simples clientes externos. Se mantienen dentro de *Integrations* por ahora, pero el roadmap propone separar `messaging/` cuando se migre, dejando en `integrations/` sólo catálogo/credenciales/eventos.
- **Bookings**: la fila `CrmBooking` vive en `models/crm.py` pero su ciclo de vida lo gobierna `BookingService` (Scheduling). Propietario lógico: Scheduling; CRM la lee para timeline.
- **`models/integrations.py`** debe partirse por propietario cuando cada módulo migre (ver `DATA_OWNERSHIP.md`); no se parte ahora porque Alembic y 60+ importadores dependen de él.

## Orquestadores cross-domain detectados

| Servicio | Dominios que coordina | Propietario propuesto |
| --- | --- | --- |
| `tool_dispatch_service` | Scheduling, CRM, WhatsApp, Voice | Tool Platform — **resuelto** con puertos (`modules/tools/application/ports.py`). |
| `outbound_voice_call_service` | CRM (`CrmLead`, `CrmVoiceCall`), Voice (`VoiceSession`, projection), Telephony (SIP, capacity, rutas), LiveKit | **Telephony** (caso de uso "llamar a un número"); CRM lo invoca vía `telephony.public` pasando identidad ya validada, y la creación de `CrmVoiceCall` pasa a CRM (evento/command). |
| `voice_session_sip_service` | Voice (dispatcher, session), Telephony (LiveKit SIP) | Telephony, consumiendo `voice.public`. |
| `booking_service` | CRM (lead, activity), Scheduling providers, Notifications pipeline, integration events | Scheduling; CRM y Notifications deberían reaccionar a eventos de booking en vez de ser llamados. |
| `whatsapp_message_service` | CRM (mensaje, actividad), Notifications (delivery status), WhatsApp client | Integrations/Messaging; la actualización de `NotificationDelivery` debería ser un callback/evento. |
| `notification_admin_service` | Integrations (plantillas, envío de prueba) | Notifications vía `integrations.public`. |
| `api/endpoints/admin/tenants.py` | Identity + 10 servicios de integraciones | Composition/admin BFF; aceptable como adaptador HTTP, pero debería consumir facades públicas. |
| `agent_service` | Tools, Voice (sesiones, LiveKit), Voice Legacy (Ultravox admin), Scheduling, WhatsApp | Agent Builder; ya consume `tools.public`. |

## Frontend

Ya existe agrupación vertical por dominio de producto en el route group `app/[locale]/(tenant)/`: `agenda`, `automations`, `crm`, `dashboard`, `integrations`, `voice-ai`, y en `components/`: `agenda`, `crm`, `dashboard`, `voice-ai`, `tenant`, `shared`, `ui`. Los clientes tipados (`lib/api/*.ts`) siguen planos. Recomendación (no implementada en esta fase): cuando un dominio crezca, co-ubicar `lib/api/<dominio>.ts`, sus Server Actions y componentes bajo `features/<dominio>/`, manteniendo `components/ui` y `components/shared` como kernel visual. No se justifica un refactor masivo ahora.
