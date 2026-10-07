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
| 2 | **Agent Builder** | `TenantAgent`/`TenantAgentVersion`, drafts, publish/unpublish/archive/delete, versionado, `AgentCompilerService` → `RuntimeSessionSpecV1`, identidad/instrucciones/comportamiento, configuración realtime y de voz provider-agnostic, bindings de tools, importación de agentes de proveedor. | `app/modules/agents/**` | **Migrado** (2026-10-01): sin dependencias hacia Ultravox; proveedores vía `VoiceProviderPort`. |
| 3 | **Voice Orchestration** | `VoiceSession`/`VoiceSessionEvent`, `SessionContextV1`, `RuntimeSessionSpecV1`, lifecycle, creación, contexto (resolución y enriquecimiento monotónico), dispatch y cleanup LiveKit del runtime, eventos del runtime, spec, token WebRTC, orquestación del endpoint de tools. | `app/modules/voice/**` | **Migrado** (2026-10-01). Sin SIP, CRM, Analytics, administración de proveedores, Voice Experiences ni Voice Legacy. |
| 4 | **Telephony** | SIP, LiveKit SIP, rutas SIP tenant, PBX/Asterisk, normalización de teléfonos, capacidad, outbound calling. | `modules/telephony/{domain,application,infrastructure,api}` + `public.py`/`wiring.py`; agente PBX `infrastructure/asterisk_agent.py` (lanzador `workers/asterisk_provisioner.py`) | **Migrado** (2026-10-02). Los callbacks públicos de Ultravox (`voice_callback_service`/`voice_callback_worker`) siguen con Voice Legacy y consumen `telephony.public`. **Siguiente módulo: Scheduling.** |
| 5 | **Tool Platform** | Registry de tools de plataforma, schema/namespace, `ResolvedToolDefinition`, resolver plataforma+custom, contrato de tres orígenes (LLM/contexto/config), dispatch, Custom HTTP Tools, credenciales cifradas, SSRF-safe HTTP. | `app/modules/tools/**` | **Migrado** (primer vertical slice) y con frontera de datos endurecida: sólo DTOs de otros módulos. Patrón de referencia. |
| 6 | **CRM** | Contactos, leads, actividades, tareas, pipeline, transiciones, métricas, call context, bookings CRM (fila `CrmBooking`), mensajes WhatsApp CRM (fila), `CrmVoiceCall`. | `models/crm.py`, `services/crm_*_service.py`, `call_summary_service.py`, `api/endpoints/{crm,crm_voice,crm_whatsapp}.py` | Legacy + `modules/crm/public.py`. |
| 7 | **Scheduling** | Disponibilidad, booking (`BookingService`), `crm_bookings`/`crm_booking_events`, Cal.com, Google Calendar, recursos, equipos, Round Robin, configuración y agenda por agente. | `modules/scheduling/{domain,application,infrastructure,api}` + `public.py`/`wiring.py` | **Migrado** (2026-10-02). Siguiente módulo: CRM. |
| 8 | **Notifications** | Domain events, reglas, destinatarios, entregas, claims con lease, reintentos, recuperación, orquestador, worker. | `models/notifications.py`, `domain/{events,notification_*}.py`, `services/notification_*`, `domain_event_service.py`, `whatsapp_notification_executor.py`, `workers/notification_worker.py` | Legacy. |
| 9 | **Integrations / Messaging** | WhatsApp (config, plantillas, mensajes, Flows), Email (Resend, templates, assets, envíos), Chatwoot, catálogo de integraciones, eventos de integración. | `modules/integrations/{domain,application,infrastructure,api,public.py,wiring.py}` (migrado, módulo 8) | **Migrado** (residuo en `app/models/integrations.py`: Forms y config legacy de Voice). |
| 10 | **Voice Experiences** | Experiencias públicas de voz, versiones, submissions, context schemas, formularios públicos, Turnstile, rate limit. | `models/{voice_experiences,voice_submissions,voice_context}.py`, `services/{public_voice_*,voice_experience*,voice_context,form,turnstile,voice_public_rate_limiter}_service.py` | Legacy. **No estaba en la propuesta inicial**: el código muestra un contexto propio con 17 archivos. |
| 11 | **Voice Legacy (Ultravox directo)** | Flujo Ultravox pre-LiveKit: `voice_service`, webhooks, ingestión, persistencia de llamadas, `TenantVoiceAgentConfig`, admin de proveedor. | `services/{ultravox_ingestion,ultravox_webhook,voice_service,voice_client,voice_webhook,voice_call,call_persistence,call_status_normalizer,voice_agent,voice_config}*.py`, `TenantVoiceAgentConfig` | Legacy + `modules/voice_legacy/public.py` (mínimo: `LegacyVoiceDefaults` para el puente de voz de Agent Builder). **Separado a propósito**: mezclarlo con Voice Orchestration ocultaría qué es rollback y qué es la ruta V2. El adapter de administración Ultravox pasó a Voice Providers. `voice_config_service` (credenciales de proveedor) debe migrar a Voice Orchestration. |
| 12b | **Voice Providers** | Registro de proveedores realtime (modelos, capacidades, parámetros, compatibilidad de voz), adapters por proveedor, credenciales de proveedor del tenant, operaciones provider-agnostic (vincular/validar agente remoto, validar voz, describir agente a importar, resolver credencial del runtime). | `app/modules/voice_providers/**` (+ legacy envuelto: `ultravox_admin_service`, `ultravox_provider_client`, `voice_config_service`, `voice_provider_admin`) | **Frontera consolidada** (2026-10-01): registro y adapters encapsulados; `public.py` no conoce ningún proveedor concreto. Módulo hermano de Voice Orchestration, nunca dentro de él. |
| 10 | **Billing** | Planes, uso, límites, alertas, pricing comparativo, admisión de llamadas y onboarding Billing. | `app/modules/billing/**` | **Migrado** (2026-10-06); posee 3 tablas. Consume minutos por `analytics.public.AnalyticsUsageFacts`. |
| 11 | **Analytics** | Hechos de llamadas, ledger de eventos, agentes de reporting, dashboards, proyección de sesiones de voz y limpieza por tenant. | `app/modules/analytics/**` | **Migrado** (2026-10-06); posee 4 tablas (`agents`, `calls`, `call_events`, `metric_snapshots_daily`). |
| — | **Shared kernel** | `db.base`, `db.session`, `db.url`, `db.mixins` (nuevo), `core.config`, `api.auth.deps`; de facto también `integration_event_service` (auditoría) y `secret_manager_service` (cifrado). | `app/db/`, `app/core/config.py` | Mantener pequeño; no mover lógica de negocio aquí. |

### Decisiones de agrupación tomadas del código

- **Voice** se divide en tres contextos (Orchestration, Experiences, Legacy) y Telephony aparte. Un único módulo `voice` tendría ~70 archivos y ocultaría el plan de retiro del flujo Ultravox directo.
- **Messaging vs Integrations**: WhatsApp y Email son canales con lógica de negocio propia (plantillas, Flows, composer), no simples clientes externos. Se mantienen dentro de *Integrations* por ahora, pero el roadmap propone separar `messaging/` cuando se migre, dejando en `integrations/` sólo catálogo/credenciales/eventos.
- **Bookings**: `CrmBooking`/`CrmBookingEvent` pertenecen a **Scheduling** (`modules/scheduling/infrastructure/models.py`); CRM los consulta sólo por `scheduling.public` (`BookingView`).
- **`models/integrations.py`** debe partirse por propietario cuando cada módulo migre (ver `DATA_OWNERSHIP.md`); no se parte ahora porque Alembic y 60+ importadores dependen de él.

## Orquestadores cross-domain detectados

| Servicio | Dominios que coordina | Propietario propuesto |
| --- | --- | --- |
| `tool_dispatch_service` | Scheduling, CRM, WhatsApp, Voice | Tool Platform — **resuelto** con puertos (`modules/tools/application/ports.py`). |
| `outbound_voice_call_service` | — | **Resuelto**: adaptador CRM delgado; el caso de uso es `telephony.public.TelephonyFacade.place_outbound_call`, el registro `CrmVoiceCall` es `crm.public.OutboundCallLedger` y el ciclo de vida de la sesión es de Voice. |
| `voice_session_sip_service` | — | **Resuelto**: ahora `telephony/application/dial_service.py`, consume `voice.public.VoiceTelephonyFacade`. |
| `booking_service` | — | **Resuelto**: `modules/scheduling/application/booking_service.py`; CRM (cliente, timeline) y Notifications (hechos) por puertos en `wiring.py`. |
| `whatsapp_message_service` | CRM (mensaje, actividad), Notifications (delivery status), WhatsApp client | Integrations/Messaging; la actualización de `NotificationDelivery` debería ser un callback/evento. |
| `notification_admin_service` | Integrations (plantillas, envío de prueba) | Notifications vía `integrations.public`. |
| `api/endpoints/admin/tenants.py` | Identity + 10 servicios de integraciones | Composition/admin BFF; aceptable como adaptador HTTP, pero debería consumir facades públicas. |
| `agent_service` | Tools, Voice (sesiones, LiveKit), Voice Legacy (Ultravox admin), Scheduling, WhatsApp | Agent Builder — **resuelto**: `AgentPorts` (`VoiceProviderPort`, `LegacyVoicePort`, `IntegrationReadinessPort`, `VoiceSessionsPort`) enlazados en `modules/agents/wiring.py`. |

## Frontend

Ya existe agrupación vertical por dominio de producto en el route group `app/[locale]/(tenant)/`: `agenda`, `automations`, `crm`, `dashboard`, `integrations`, `voice-ai`, y en `components/`: `agenda`, `crm`, `dashboard`, `voice-ai`, `tenant`, `shared`, `ui`. Los clientes tipados (`lib/api/*.ts`) siguen planos. Recomendación (no implementada en esta fase): cuando un dominio crezca, co-ubicar `lib/api/<dominio>.ts`, sus Server Actions y componentes bajo `features/<dominio>/`, manteniendo `components/ui` y `components/shared` como kernel visual. No se justifica un refactor masivo ahora.


### Identity / Tenancy (Module 9)

Path: `backend/app/modules/identity/`. Identity owns the five tables documented in `DATA_OWNERSHIP.md`. `public.py` is the cross-module facade; Auth0 and temporary foreign-module adapters are composed by `wiring.py`.

Billing ORM boundary: tenant foreign keys remain in the database without ORM relationships to Identity; ORM navigation remains within Billing.
