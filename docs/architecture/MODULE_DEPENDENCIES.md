# Dependencias entre módulos

Generado a partir del grafo AST de imports de `backend/app/` (incluye imports locales dentro de funciones). Cada celda cuenta **pares únicos `archivo → archivo`** del dominio de la fila al de la columna. Shared kernel (`app.db`, `app.core.config`) y `main.py` se excluyen.

## Matriz antes de esta iteración (`develop@f52e82f`)

```text
fila → columna      Agents Billing CRM Identity Integr Notif Sched Teleph Tools Voice VoiceExp VoiceLeg
Agents                 -      .     .     5       3     .     1     .     10     4      .        2
Billing/Analytics      .      -     .     3       .     .     .     .      .     .      .        .
CRM                    .      5     -    12       7     .     1     2      .     .      .        3
Identity               .      7     1     -      12     .     3     .      .     .      .        2
Integrations           .      .     8     8       -     2     5     .      .     2      .        2
Notifications          .      .     3     4      12     -     .     .      .     .      .        .
Scheduling             .      .    13     1      21     3     -     .      .     2      .        .
Telephony              .      1     3     2       8     .     .     -      .     9      4        4
Tools                  1      .     3     5       6     .     1     .      -     7      .        .
Voice (Orchestr.)      5      4    12    10       7     1     .     2      1     -      2        7
Voice Experiences      .      1     6    13       6     .     .     4      .     4      -        3
Voice Legacy           7      4     5     2      12     1     .     4      .     2      .        -
```

## Fila Tools después de esta iteración

```text
                    Agents CRM Identity Integr Sched Voice   (todas vía public.py / allowlist shared)
Tools                  1    1     4       5      1     6
```

| Métrica (Tool Platform) | Antes | Después |
| --- | --- | --- |
| Imports de tools hacia internals de otros dominios | 16 | **0** |
| Imports de otros dominios hacia internals de tools | 11 | **0** |
| Consumidores entrantes | `agent_service`, `agent_compiler_service`, `voice_runtime` (11 imports a 7 archivos) | los mismos 3, sólo `app.modules.tools.public` |
| Ciclos de import dentro de tools | 1 (`custom_http_tool_executor ↔ tool_dispatch_service`) | 0 (test automático) |

Las dependencias restantes de tools hacia legacy son únicamente shared kernel explícito (`TOOLS_LEGACY_ALLOWED` en `backend/test_module_boundaries.py`): `api.auth.deps`, `core.config`, `db.*`, `integration_event_service` (auditoría) y `secret_manager_service` (cifrado). Los feature flags pasan por `identity.public` desde el hardening de 2026-10-01.

### Hardening de la frontera de datos (2026-10-01)

Una frontera de imports no basta si por ella viajan filas ORM o `Any`. Métricas de Tool Platform:

| Métrica | Antes | Después |
| --- | --- | --- |
| Modelos ORM de otros módulos que cruzan la frontera de Tools | 6 (`VoiceSession`, `TenantAgent`, `TenantAgentVersion` por relación, `CrmContact`, `CrmLead`, `TenantWhatsAppTemplate` en `WhatsAppTemplateRef._row`) | **0** |
| `Any` como entidad cross-module en `ToolPorts` | 7 (`sessions.get` return, `record_event`/`enrich_context` session, `contact`, `lead`, `tuple[Any, Any]` de CRM) | **0** (queda `notes: Any`, payload libre del LLM) |
| `Any` como entidad en facades públicas usadas por Tools | 8 (las 7 equivalentes en `VoiceSessionFacade`/`CrmFacade` + `_row: Any`) | **0** |
| Imports de rutas legacy de tools en tests | 58 en 14 archivos | **0** |
| Excepciones de arquitectura para Tools | 8 en la allowlist legacy | 7 (sale `tenant_feature_service`) |

DTOs que cruzan ahora la frontera: `ToolSessionView`/`ToolBindingView` (Voice), `ContactRef`/`LeadRef` (CRM), `WhatsAppTemplateContract`/`WhatsAppSendOutcome` (Integrations), `BookingSummary` (Scheduling); `FeatureFlags` (Identity) sólo devuelve `bool`/`None`.

## Ciclos entre dominios detectados (antes)

Ciclos bidireccionales a nivel de dominio: Agents↔Tools, Agents↔Voice, Agents↔VoiceLegacy, CRM↔Identity, CRM↔Integrations, CRM↔Scheduling, CRM↔Telephony, CRM↔VoiceLegacy, Identity↔Billing, Identity↔Integrations, Identity↔Scheduling, Identity↔VoiceLegacy, Integrations↔Notifications, Integrations↔Scheduling, Integrations↔Voice, Integrations↔VoiceLegacy, Telephony↔Voice, Telephony↔VoiceExperiences, Telephony↔VoiceLegacy, Tools↔Voice, Voice↔VoiceExperiences, Voice↔VoiceLegacy.

Ciclos a nivel de archivo Python (imports reales): `agent_service ↔ ultravox_admin_service` (vigente, resuelto con import perezoso) y `custom_http_tool_executor ↔ tool_dispatch_service` (**eliminado**).

Estado de los ciclos que tocan Tools tras esta iteración:
- **Tools↔Voice**: tools sólo usa `voice.public` (`SessionContextV1`, errores, `VoiceSessionFacade`). Voice usa sólo `tools.public` desde el endpoint del runtime. Ciclo a nivel de API pública, **permitido**: `SessionContextV1` es un contrato del runtime y la invocación de tools es un caso de uso de la sesión.
- **Agents↔Tools**: Agent Builder usa `tools.public`; tools consulta `agents.public` sólo para "¿esta tool custom está en una versión publicada?". **Cuestionable pero aceptado**: la alternativa (evento o puerto inverso) no reduce acoplamiento real para una query de lectura.

## Clasificación de dependencias

Leyenda: ✅ permitida · ⚠️ cuestionable · ❌ eliminar · 🔁 circular.

| Dependencia | Evidencia | Clasificación | Mecanismo objetivo |
| --- | --- | --- | --- |
| Todos → Identity (`api.auth.deps`, `models.identity.Tenant`, `tenant_feature_service`) | ~60 imports | ✅ | `identity.public` (`AuthContext`, `require_roles`, `FeatureFlags`); FK a `tenants.id` es aceptable. |
| Todos → `integration_event_service` | auditoría transversal | ✅ (shared) | Mover a `shared/audit` cuando migre Integrations. |
| Tools → Scheduling / CRM / WhatsApp | handlers de dispatch | ✅ **resuelto** | Puertos `SchedulingToolPort`, `CrmToolPort`, `MessagingToolPort` (commands síncronos: la LLM espera el resultado). |
| Tools → Voice (`VoiceSessionService`, `VoiceSession`) | dispatch + eventos + enrich | ✅ **resuelto** | Puerto `VoiceSessionToolPort` + `voice.public`; sólo `ToolSessionView` y operaciones por `session_id`. |
| Tools → Integrations (`TenantWhatsAppTemplate`, `WhatsAppTemplateService`) | contrato WhatsApp | ✅ **resuelto** | Query service `WhatsAppFacade.get_approved_template_contract` → `WhatsAppTemplateContract`. |
| Tools → Agents (`TenantAgentVersion`) | tool en uso | ✅ **resuelto** | `AgentsFacade.is_tool_bound_to_published_version`. |
| Agents → Tools | catálogo, validación, compilación | ✅ **resuelto** | `tools.public`. |
| Agents → Voice (`voice_session_service`, `livekit_runtime_backend`) | cierre de sesiones al borrar agente | ⚠️ | Command en `voice.public` (`close_sessions_for_agent`). |
| Agents ↔ Voice Legacy (`ultravox_admin_service`) 🔁 | preflight de voz, importación de agentes Ultravox | ⚠️ | Puerto `VoiceProviderCatalogPort` en Agents, implementado por el adapter Ultravox. |
| Agents → Scheduling / WhatsApp config | preflight `required_integration` | ⚠️ | Query `is_configured(tenant_id)` en cada `public.py`. |
| Voice → Agents (`agent_compiler_service`, `models.agents`) | spec del runtime | ✅ | `agents.public.compile_runtime_spec`. |
| Voice → CRM (`crm_contact/lead/call_context` services, `models.crm`) | resolución de contexto, proyección | ⚠️ | Query service `crm.public` (resolver por teléfono/id); la proyección a `CrmActivity` debería ser evento `voice.session.completed`. |
| Voice → Telephony 🔁 | QA SIP (`voice_runtime` endpoint) | ✅ | Sólo `telephony.public.TelephonyFacade.dial_qa_session`; Telephony consume `voice.public` (ciclo de módulo bidireccional, sólo vía `public.py` y wiring perezoso). |
| Voice → Voice Legacy (`voice_config_service`) | credenciales del runtime | ❌ | Mover `TenantVoiceProviderConfig` + `VoiceConfigService` a Voice Orchestration. |
| Telephony → Voice 🔁 | outbound y SIP QA | ✅ | **Resuelto**: `VoiceTelephonyPort` → `voice.public.VoiceTelephonyFacade`; `TelephonySessionView`, nunca el ORM. |
| Telephony → CRM | outbound, capacidad legacy | ✅ | **Resuelto**: `OutboundCallLedger` y `CallLoadPort` (`crm.public`); `CrmVoiceCall` lo crea CRM. |
| Telephony → Voice Experiences / Legacy (`voice_callback_service`) | callbacks públicos Ultravox | ⚠️ | Queda con Voice Legacy hasta su retiro. |
| CRM → Telephony | acción "llamar", métricas | ✅ | El adaptador CRM llama a `telephony.public`; el dashboard usa `voice_capacity_report_service`. |
| CRM → Integrations (email, WhatsApp) | acciones del lead | ✅ si vía `integrations.public` | Commands. |
| CRM ↔ Scheduling 🔁 | CRM endpoint → `booking_service`; booking → `CrmActivity`, `CrmLead` | ⚠️ | Scheduling valida lead vía `crm.public`; la actividad CRM se registra por evento `booking.*` (ya existe `NotificationEventPipeline`/`domain_events`). |
| Scheduling → Notifications (`notification_event_pipeline`) | booking crea domain events | ✅ | Es exactamente el patrón de eventos deseado; exponer `notifications.public.publish(...)`. |
| Integrations ↔ Notifications 🔁 | `whatsapp_message_service` → `NotificationDeliveryStatusService`; notificaciones → WhatsApp | ⚠️ | Notifications → `integrations.public` (command send); el status de entrega vuelve como callback/evento, no import directo. |
| Integrations → CRM (`crm_activity_service`, `models.crm`) | timeline de mensajes/emails | ⚠️ | Evento `message.sent` → CRM, o `crm.public.record_activity`. |
| Identity → Integrations (`admin/tenants.py` → 10 servicios) | panel admin | ⚠️ | Es un BFF de administración: consumir `public.py` de cada módulo. |
| Identity ↔ Billing 🔁 | onboarding crea plan/uso; billing lee tenant | ⚠️ | Onboarding → `billing.public.provision_plan`. |
| Voice Experiences → Telephony / Voice | callbacks, rutas SIP, context schemas | ⚠️ | `telephony.public`, y mover `voice_context` (context schemas) a Voice Experiences. |

## Caso `tool_dispatch_service` (resuelto)

| Handler | Antes | Después | Mecanismo |
| --- | --- | --- | --- |
| `_handle_check_availability` | `BookingService(db)` | `ports.scheduling.get_available_slots` | Query service vía puerto |
| `_handle_create_booking` | `BookingCreateRequest` + `BookingService(db)` | `ports.scheduling.create_lead_booking` (el DTO HTTP de CRM ya no se construye en tools) | Command vía puerto |
| `_handle_create_lead` | `CrmContactService` + `CrmLeadService` + `VoiceSessionService.enrich_context` | `ports.crm.get_or_create_open_lead` + `ports.sessions.enrich_context` | Command vía puerto |
| `_handle_send_whatsapp` | `WhatsAppMessageService(db)` | `ports.messaging.send_template` | Command vía puerto |
| Carga de sesión / eventos | `VoiceSessionService(db)` | `ports.sessions.get/record_event` | Facade pública |

Por qué puertos y no eventos: los cuatro casos requieren respuesta síncrona para la LLM dentro de la llamada. `wiring.default_tool_ports(db)` es el único punto que conoce las implementaciones.

## Caso `outbound_voice_call_service` (resuelto, 2026-10-02)

Propietario: **Telephony**. `OutboundVoiceCallService` quedó como adaptador CRM (HTTP ↔ comando). El caso de uso `telephony.public.TelephonyFacade.place_outbound_call(command, ledger)` conserva el orden exacto (sesión → ruta bloqueada → capacidad → vínculo → `voice.outbound.requested` → dispatch → `runtime_ready` → participante SIP → `voice.sip.dial.started` → answered/error → limpieza), con CRM como `OutboundCallLedger` y Voice como `VoiceTelephonyPort`. La proyección sigue síncrona vía `CallProjectionPort` (aún no por eventos).

## Reglas de importación vigentes

Aplicadas por `backend/test_module_boundaries.py`:

1. Un módulo en `app/modules/<a>/` sólo puede importar de otro módulo `app/modules/<b>/public.py`.
2. Código legacy (fuera de `app/modules/`) sólo puede importar `app.modules.<x>.public`. Excepciones de composition root: `app/main.py` puede montar `app.modules.<x>.api.*` y `app/models/__init__.py` registra `app.modules.<x>.infrastructure.models` para Alembic. Los shims marcados `TEMPORARY compatibility shim` están exentos.
3. Tool Platform no importa servicios/modelos/schemas legacy de otros dominios, salvo la allowlist de shared kernel.
4. `app.modules.tools.domain` no importa application/infrastructure/api en runtime (sólo `TYPE_CHECKING`) ni otros módulos salvo `voice.public` (`SessionContextV1` es parte del contrato de invocación).
5. El dispatcher no importa CRM, Scheduling ni Integrations: sólo puertos.
6. ~~Ningún archivo de producción usa las rutas legacy de tools~~ / 7. ~~Las rutas legacy son alias~~: retiradas junto con los 18 shims de Tool Platform (2026-10-01).
8. No hay ciclos de import dentro de `app.modules.tools`.
13. Agent Builder no importa código legacy de otros dominios salvo `AGENTS_LEGACY_ALLOWED` (`api.auth.deps`, `db.*`, `integration_event_service`); `RuntimeSessionSpecV1` llega desde `voice.public`.
14. Ningún archivo de `app.modules.agents` importa (ni siquiera de forma perezosa) `app.services.ultravox_*` ni `app.services.voice_provider_admin`; esos adapters no importan Agent Builder, ni ningún `app.modules.*` en runtime.
15. Ninguna componente fuertemente conexa del grafo de imports (incluidos los perezosos) contiene a la vez un módulo de Agent Builder y un adapter de proveedor.
16. `app.modules.agents.domain` es puro (sólo dominio propio y `voice_providers.public` para el registro); `application` no importa `api` en runtime (los requests HTTP sólo bajo `TYPE_CHECKING`).
17. Nadie navega las relaciones eliminadas `.agent_version` / `.voice_agent_config`.
19. Voice Orchestration no importa código legacy salvo `VOICE_LEGACY_ALLOWED` (`api.auth.deps`, `core.config`, `db.*`, `security.voice_runtime_auth`): ni CRM/Analytics, ni Telephony/SIP, ni adapters de proveedor, ni Voice Legacy, ni `tenant_feature_service`.
20. `app.modules.voice.domain` es puro: sólo dominio propio y `agents.public` (value objects del contrato de runtime), sin SQLAlchemy/FastAPI/LiveKit/httpx.
21. El ORM de Voice (`app.modules.voice.infrastructure.models`) sólo lo importa Voice, el registro de modelos y los shims.
22. `voice.public`, `voice_providers.public` y `agents.public` se importan sin cargar casos de uso, ORM, LiveKit, servicios CRM/Analytics ni adapters (verificado en un proceso limpio).
23. Voice Providers sólo toca código legacy desde `infrastructure/ultravox.py` (adapter) e `infrastructure/credentials.py`; `public`/`application`/`domain` no conocen ningún proveedor concreto ni `UltravoxProviderError`.
24. Ninguna componente fuertemente conexa contiene Voice y un adapter de proveedor; los adapters sólo pueden importar `voice_providers.public`.
25. Telephony sólo toca código legacy compartido (`TELEPHONY_LEGACY_ALLOWED`: `core.config`, `db.*`, `integration_event_service`, `secret_manager_service`); nunca `app.models.voice_sessions`, `app.models.crm`, internals de Voice/Voice Providers, `VoiceCallProjectionService`, dispatcher ni backend de runtime (`TELEPHONY_FORBIDDEN_PREFIXES`).
26. `app.modules.telephony.domain` es puro (sin SQLAlchemy/FastAPI/LiveKit/CRM/Voice/httpx) y `application` no importa `api`.
27. El ORM de Telephony (`TenantSipRoute`) sólo lo importa Telephony y el registro de modelos; nadie importa las rutas viejas (`voice_phone_service`, `livekit_sip_service`, `voice_sip_route_service`, `voice_capacity_service`, `voice_session_sip_service`, `asterisk_provisioning_*`).
28. No hay shims: `KNOWN_SHIMS` está vacío; un shim nuevo debe registrarse ahí. Los procesos de entrada (`app.workers.asterisk_provisioner`) pueden importar el agente directamente (raíz de composición).
29b. Excepción temporal (deuda de **Voice Legacy**, no de Telephony): sólo `voice_call_service` y `voice_callback_service` pueden leer la contraseña SIP descifrada vía `SipRouteFacade.get_connection`/`SipRouteConnection` (`SIP_CREDENTIAL_CONSUMERS`); cualquier otro consumidor rompe el test. Se retira al jubilar esos flujos Ultravox directos.
29. Ninguna componente fuertemente conexa contiene Telephony y un adapter de proveedor; los adapters y `voice_provider_config_store` no importan ningún módulo salvo `voice_providers.public`.

## Reglas de datos vigentes

Aplicadas por `DataBoundaryTests` en `backend/test_module_boundaries.py`:

9. Las APIs críticas (`VoiceSessionFacade`, `VoiceTelephonyFacade`, `TelephonyFacade`, `SipRouteFacade`, `CapacityFacade`, los puertos de Telephony, `CrmFacade`, `WhatsAppFacade`, `SchedulingFacade`, `AgentsFacade`, `FeatureFlags` y los cuatro `Protocol` de `ToolPorts`) no declaran en parámetros ni retorno ninguna clase ORM ni `Any` directo. `Any` sólo se permite como tipo de valor de un `dict`/`Mapping` de payload, más la excepción explícita `create_lead_booking(notes)`.
10. Los DTOs públicos son `@dataclass(frozen=True)` y sus campos no contienen ORM ni `Any` directo.
11. Ningún archivo de `app.modules.tools` navega atributos de filas ORM ajenas (`agent_version`, `session_context_json`, `runtime_binding_json`, `_row`).
12. Las mutaciones sobre datos de otro módulo se piden por id y DTO; el propietario recarga sus filas y valida tenant (`VoiceSessionFacade.enrich_context`, `VoiceSessionFacade.release_sessions_of_deleted_agent`).
18. Las APIs y DTOs de Agent Builder, Voice Providers y Voice Legacy (`AgentsFacade`, `AgentPorts`, `VoiceProviderFacade`, `VoiceLegacyFacade`, `PublishedAgent`, `AgentDisplay`, `ImportedAgent`, `AgentToolBindingView`, `ProviderAgentSnapshot`, `ProviderAgentImport`, `ProviderToolRef`, `ProviderVoiceSelection`, `LegacyVoiceDefaults`) cumplen 9-10 y además no exponen ningún tipo de un módulo `*ultravox*`.

## Migración de Agent Builder (2026-10-01)

Medido con el mismo grafo AST (imports perezosos incluidos), `develop@32c624d` → esta rama:

| Métrica | Antes | Después |
| --- | --- | --- |
| Imports Agents → implementaciones de proveedor (`ultravox_*`, `voice_provider_admin`) | 2 (`agent_service → ultravox_admin_service`, `→ ultravox_provider_client`) | **0** |
| Imports de otros dominios → internals de Agents | 10 (`voice_runtime`, `voice_session_service`, `voice_call_projection_service`, `voice_call_service`, `runtime_session`, `ultravox_admin_service` ×3, `voice_provider_admin` service y endpoint) | **0** (sólo `agents.public`; `main.py` monta el router y `models/__init__` registra el ORM) |
| ORM de Agents cruzando la frontera pública | `TenantAgent`/`TenantAgentVersion` leídos por 4 servicios de Voice + relaciones `VoiceSession.agent`/`.agent_version`; `TenantVoiceAgentConfig` vía relación ORM en Agents | **0** (DTOs y relaciones eliminadas; FKs intactas) |
| Imports legacy `app.models.agents` (app + tests) | 7 en app + 9 en tests | **0** |
| Imports legacy `app.services.agent_*` / `voice_selection_service` | 4 en app + 4 en tests | **0** |
| Ciclos de archivo que involucran Agent Builder | 1 directo (`agent_service ↔ ultravox_admin_service`) | **0** con adapters; queda una componente Agents ↔ Tools ↔ Voice sólo a través de `public.py` y wiring perezoso |
| Shims de Tool Platform | 18 | **0** |
| Shims de Agent Builder creados | — | **0** (sin consumidores en `develop` ni en ramas abiertas) |

## Migración de Voice Orchestration (2026-10-01)

Mismo grafo AST (imports perezosos incluidos), `develop@37b259c` → esta rama. "Voice" antes = `voice_session_service`, `contact_resolution_service`, `voice_runtime_dispatcher`, `livekit_runtime_backend`, `models/voice_sessions`, `schemas/{session_context,runtime_session,voice_sessions,voice_credentials}`, `api/endpoints/voice_runtime`, `modules/voice/public`.

| Métrica | Antes | Después |
| --- | --- | --- |
| Imports Voice → internals de CRM | 3 | **0** |
| Imports Voice → internals de Analytics (proyección) | 1 | **0** |
| Imports Voice → internals de Agents | 0 | **0** |
| Imports Voice → internals de Telephony | 2 (`voice_session_sip_service`, `voice_phone_service`) | **0** (`telephony.public`) |
| Imports Voice → internals de proveedor | 2 (`voice_registry`, `voice_config_service`) | **0** (`voice_providers.public`) |
| Imports Voice → `tenant_feature_service` | 1 | **0** (`identity.public`) |
| Módulos fuera de Voice que importan el ORM de Voice | 4 | 3 (sólo vía shim: Telephony ×2 y `voice_call_service`; la proyección ya usa DTOs) |
| Imports legacy `app.models.voice_sessions` | 8 app + 4 tests + 1 script | 3 app (legacy) + 1 script, 0 tests |
| Imports legacy `voice_session_service` | 5 app + 6 tests | 2 app (Telephony), 0 tests |
| Imports específicos de proveedor en `voice_providers.public` | 2 (`ultravox_provider_client`, `voice_provider_admin`) | **0** |
| Componentes conexas con Voice | 1 (14 archivos) | 1 (20 archivos, sólo vía `public.py`/wiring; crece porque la proyección legacy pasa a consumir `voice.public`) |
| Componentes conexas con Voice + adapter de proveedor | 0 | **0** (regla automática) |
| Shims de Voice creados | — | **4** (con consumidores legacy reales) |

## Migración de Telephony (2026-10-02)

Mismo grafo AST (imports perezosos incluidos), `develop@76176f4` → esta rama. "Telephony" antes = `voice_phone_service`, `livekit_sip_service`, `voice_sip_route_service`, `voice_capacity_service`, `voice_session_sip_service`, `asterisk_provisioning_service`, `schemas/asterisk_provisioning`, `api/endpoints/asterisk_provisioning`, `workers/asterisk_provisioner` y `outbound_voice_call_service`.

| Métrica | Antes | Después |
| --- | --- | --- |
| Imports Telephony → internals de Voice | 8 | **0** (`voice.public`) |
| Imports Telephony → internals de CRM | 2 (`models.crm`) | **0** (`crm.public`) |
| Imports Telephony → internals de proveedor / Analytics | 0 / 0 | **0 / 0** |
| ORM de Voice / CRM cruzando Telephony | 2 / 2 | **0 / 0** |
| Imports legacy `models.voice_sessions` · `voice_session_service` · `livekit_runtime_backend` · `voice_runtime_dispatcher` | 3 · 2 · 2 · 1 (app) | **0 · 0 · 0 · 0** |
| Shims de Voice | 4 | **0** (eliminados) |
| Importadores de las rutas SIP/Asterisk antiguas fuera de Telephony | 15 | **0** (queda `crm_voice → outbound_voice_call_service`, el adaptador CRM) |
| Componente conexa (grafo de archivos, incluye `app.models`/`db`) con Voice/Telephony | 1 (20 archivos) | 1 (28 archivos; crece por el wiring perezoso Telephony ↔ Voice y la proyección, sólo vía `public.py`) |
| Componentes conexas con Telephony + adapter de proveedor | 0 | **0** (regla automática; se evitó un ciclo separando `VoiceProviderConfigStore`) |
| Tests backend (suite CI) | 1767 métodos `test_*` (develop) | 1788 métodos `test_*` (1662 ejecutados en la suite CI por módulo; +4 PostgreSQL y +4 de Voice Runtime se ejecutan aparte) |
