# Migración a monolito modular

Objetivo: límites de módulo mantenibles dentro del **mismo backend y el mismo deployment**. Sin microservicios, sin bases separadas, sin bus distribuido. Ver `MODULE_MAP.md`, `MODULE_DEPENDENCIES.md` y `DATA_OWNERSHIP.md`.

## Patrón de migración por módulo

Aplicado en Tool Platform; repetir por módulo, un PR por módulo:

1. **Publicar la frontera primero**: crear/ampliar `app/modules/<m>/public.py` con sólo lo que los consumidores reales usan.
2. **Mover archivos con `git mv`** a `app/modules/<m>/{domain,application,infrastructure,api}/`. Como la ruta vieja pasa a ser un shim, Git no ve un rename puro: la historia se consulta con `git log --follow -C -- <ruta nueva>`.
3. **Shim en la ruta legacy**, alias de `sys.modules` (mismo objeto módulo: sin lógica duplicada, los `unittest.mock.patch("app.services.x.Y")` siguen funcionando). Marcado `TEMPORARY compatibility shim`.
4. **Reescribir consumidores de producción** a `app.modules.<m>.public`.
5. **Sustituir imports a internals de otros dominios** por su `public.py`; usar puertos (`Protocol`) sólo donde el módulo ejecuta commands en varios dominios.
6. **Frontera de datos, no sólo de imports**: ninguna API pública devuelve ni recibe filas ORM de otro módulo, ni `Any` en lugar de una entidad. Se cruzan DTOs `@dataclass(frozen=True)` del módulo propietario (`ToolSessionView`, `ContactRef`/`LeadRef`, `WhatsAppTemplateContract`...). Las operaciones que mutan datos de otro módulo se piden por id (`enrich_context(session_id, contact=ContactRef, ...)`) y el propietario recarga sus filas y aplica sus invariantes.
7. **Tests de frontera** en `backend/test_module_boundaries.py`: imports (allowlist legacy del módulo, pureza de `domain`, alias de shims) y datos (`DataBoundaryTests`: anotaciones de las APIs críticas y campos de los DTOs sin ORM ni `Any`, sin navegación de atributos ORM ajenos).
8. Suite completa, `compileall`, `alembic heads` (una sola head), lint/typecheck/build frontend, `git diff --check`.

Shims: sólo si existe un consumidor real (código, tests, scripts, migraciones o una rama abierta). Se retiran en el PR siguiente cuando ya no queda ninguno. Tool Platform: 18 shims creados y retirados en la migración de Agent Builder. Agent Builder: 0 shims (ningún consumidor restante ni en `develop` ni en ramas abiertas).

Estructura objetivo por módulo:

```text
app/modules/<m>/
├── public.py          # única API cross-module
├── wiring.py          # (opcional) composition root: binds puertos a facades
├── domain/            # reglas puras, sin DB/HTTP en runtime
├── application/       # casos de uso, puertos
├── infrastructure/    # ORM, clientes externos, cifrado
└── api/               # router FastAPI + schemas HTTP
```

`main.py` sigue montando routers de forma explícita (`app.include_router(...)`). Se evaluó un `module.register(app)` y se descartó por ahora: no aporta nada con ~30 routers y hace menos trazable el orden de registro y el OpenAPI.

## Roadmap

Orden validado contra el grafo real: primero módulos con pocos consumidores entrantes y dependencias salientes ya acotadas.

| Orden | Módulo | Complejidad | Estado |
| --- | --- | --- | --- |
| 1 | Tool Platform | Baja | **Hecho** |
| 2 | Agent Builder | Media | **Hecho** |
| 3 | Voice Orchestration | Alta | **Hecho** |
| 4 | Telephony | Media-alta | **Hecho** |
| 5 | Scheduling | Alta | **Hecho** |
| 6 | CRM | Alta | **Siguiente** |
| 7 | Notifications | Media | |
| 8 | Integrations / Messaging | Alta | |
| 9 | Identity / Tenancy | Media (muchos consumidores, poca lógica) | |
| 10 | Billing | Baja | |
| 11 | Analytics | Media | |
| — | Voice Experiences | Media | Tras CRM |
| — | Voice Providers | Media | **Frontera consolidada** (registro, adapters, credenciales) |
| — | Voice Legacy | — | **No migrar**: aislado tras `voice_legacy.public` (mínimo); retirar cuando `voice_runtime_v2` sea el único camino |

### 1. Tool Platform — hecho (patrón de referencia)

- **Ownership**: `tenant_tools`, `tenant_http_tool_configs`, `tenant_tool_credentials`; schema de `runtime_binding_json["tools"][].config`.
- **Entrantes**: Agent Builder (`agent_service`, `agent_compiler_service`), Voice (`api/endpoints/voice_runtime.py`), `main.py` (router).
- **Salientes** (sólo `public.py`): `voice` (`ToolSessionView`, `VoiceSessionFacade.get_tool_session/record_event/enrich_context`), `crm` (`ContactRef`, `LeadRef`, `CrmFacade`), `scheduling` (`BookingSummary`), `integrations` (`WhatsAppTemplateContract`, `WhatsAppSendOutcome`), `agents` (bool), `identity` (`FeatureFlags`). Shared kernel: `integration_event_service`, `secret_manager_service`, `api.auth.deps`, `core.config`, `db.*`.
- **API pública**: `ToolDispatchService`, errores `Tool*Error`, `ToolResolverService`, `ToolCatalogService`, `PlatformToolContractService`/`Error`, `ResolvedToolDefinition`, `get_tool`, `from_platform`, `ToolRegistryValidationError`, `is_custom_tool_credential_ready`.
- **Frontera de datos (hardening, 2026-10-01)**: ningún ORM de otro módulo entra en Tools (antes `VoiceSession` + `TenantAgent`/`TenantAgentVersion` por relación, `CrmContact`, `CrmLead`, `TenantWhatsAppTemplate` oculto en `_row`). `ToolPorts` no usa `Any` para entidades. El enriquecimiento monotónico de `SessionContextV1` sigue siendo responsabilidad exclusiva de Voice (`VoiceSessionService.enrich_context_by_ids` recarga las filas por id y aplica las mismas reglas y códigos).
- **Shims**: retirados (2026-10-01) tras comprobar cero consumidores.
- **Excepciones de arquitectura restantes**: allowlist de shared kernel (`api.auth.deps`, `core.config`, `db.base`, `db.mixins`, `db.session`, `integration_event_service`, `secret_manager_service`); `notes: Any` en `SchedulingToolPort.create_lead_booking` (texto libre del LLM); `voice.public` en la capa `domain` (`SessionContextV1` es parte del contrato de invocación).

### 2. Agent Builder — hecho (2026-10-01)

Estructura: `app/modules/agents/{domain/{contracts,errors,views,voice_selection}.py, application/{service,compiler,queries,ports}.py, infrastructure/models.py, api/{router,schemas}.py, public.py, wiring.py}`.

- **Ownership**: `tenant_agents`, `tenant_agent_versions` (ORM en `infrastructure/models.py`, registrado en `app/models/__init__.py` para Alembic). Sin tablas nuevas ni cambio de schema; FK `voice_agent_config_id` intacta.
- **Contratos**: value objects puros (`AgentIdentity`, `AgentInstructions`, `AgentBehavior`, `AgentVoiceConfig`, `AgentToolBinding`, `ProviderAgentReference`, `ProviderManagedOverrides`) en `domain/contracts.py`; requests/responses HTTP en `api/schemas.py`. `RuntimeSessionSpecV1` sigue siendo un contrato compartido propiedad de Voice (`app/schemas/runtime_session.py`); importa los value objects desde `agents.public`, por eso `agents.public` sólo carga dominio al importarse y resuelve los casos de uso de forma perezosa.
- **API pública** (`agents.public`): `AgentsFacade.lock_published_agent`, `get_agent_status`, `get_tool_bindings`, `describe_agent`, `agent_names`, `is_tool_bound_to_published_version`, `compile_runtime_spec`, `import_provider_agent`; `validate_voice_settings`; DTOs `PublishedAgent`, `AgentDisplay`, `ImportedAgent`, `AgentToolBindingView`; errores de dominio. Ningún ORM cruza la frontera.
- **Puertos** (`application/ports.py`): `VoiceProviderPort`, `LegacyVoicePort`, `IntegrationReadinessPort`, `VoiceSessionsPort`, agrupados en `AgentPorts` y enlazados en `wiring.py` a `voice_providers.public`, `voice_legacy.public`, `scheduling.public`/`integrations.public` y `voice.public`.
- **Entrantes**: Voice (`voice_session_service`, `voice_runtime`, dispatcher, proyección, historial), Tool Platform, endpoint de importación de proveedores, `runtime_session` (contratos) — todos vía `agents.public`.
- **Salientes**: `tools.public`, `voice.public` (sesiones), `voice_providers.public`, `voice_legacy.public`, `scheduling.public`, `integrations.public`, `identity.public`; shared: `integration_event_service`, `api.auth.deps`, `db.*`, `schemas.runtime_session`.
- **Dependencia mutua a nivel público**: Agents ↔ Voice ↔ Tools forman una componente conexa sólo a través de `public.py` y del wiring perezoso (Voice lee agentes publicados; Agents pide liberar sesiones y resolver tools). Es inherente al reparto actual de ownership y no incluye ningún archivo de proveedor.

#### Ciclo `AgentService ↔ UltravoxAdminService` — eliminado

Antes: `AgentService` importaba (perezosamente) `UltravoxAdminService`/`ultravox_provider_client` en publish, en el preflight de voz y al vincular un agente remoto; `UltravoxAdminService.import_agent` creaba el agente llamando a `AgentService.create_agent` y escribía `provider_extensions`.

Ahora:

```text
AgentService ── VoiceProviderPort ── agents/wiring ── voice_providers.public.VoiceProviderFacade
                                                            │ (registro de proveedores)
                                                            ▼
                                              voice_provider_admin ── UltravoxAdminService ── Ultravox
```

- `VoiceProviderPort` expresa necesidades de Agent Builder (`supports_provider_managed`, `link_provider_agent`, `validate_provider_execution`, `validate_voice`), no la API de Ultravox. Errores: `VoiceProviderError(code)` neutro; los códigos visibles no cambian (`voice_not_accessible`, `provider_agent_has_unsupported_client_tools`, ...).
- **Desviación deliberada del diseño previsto**: la facade de proveedores no vive en `voice.public` sino en `voice_providers.public`. `voice.public` depende de las sesiones, y éstas de `agents.public`; si los DTOs de proveedor vivieran ahí, el adapter Ultravox quedaría en la misma componente fuertemente conexa que `AgentService` (ciclo transitivo, detectado al medir el grafo). Además, el adapter ya no importa ningún módulo en runtime: devuelve `UltravoxAgentImport` (su propio modelo) y la facade lo traduce a `ProviderAgentImport`.
- **Importación invertida**: el endpoint `POST /integrations/voice/providers/{provider}/agents/{agent_id}/import` (sin cambios de URL ni payload) orquesta `VoiceProviderFacade.get_agent_import` → `AgentsFacade.import_provider_agent`. Sólo Agent Builder escribe `TenantAgent`, `TenantAgentVersion`, `runtime_binding_json` y `provider_extensions`; la forma persistida es idéntica a la anterior (verificado ejecutando el `import_agent` original de `develop` con el mismo payload).
- **Preview de voz externa**: el endpoint convierte `AgentVoiceConfig` (cuerpo HTTP sin cambios) a `ProviderVoiceSelection`; el adapter valida el soporte (`ensure_external_voice_supported`), el endpoint aplica las reglas de ajustes de Agent Builder (`agents.public.validate_voice_settings`) y después pide la preview. El orden de errores se conserva.
- **Tests que lo protegen**: `test_module_boundaries.py` prohíbe imports (incluso perezosos) Agents → `app.services.ultravox_*`/`voice_provider_admin`, el inverso, imports de módulos desde los adapters, y cualquier componente fuertemente conexa que contenga a la vez Agents y un adapter. `test_agent_builder_provider_agnostic.py` ejecuta link, validación de voz, publish e importación con un proveedor ficticio `acme` (registrado sólo en el catálogo de Voice durante el test) y con el adapter Ultravox bloqueado.

#### Dependencia legacy `TenantAgentVersion -> TenantVoiceAgentConfig` — aislada

- Se mantiene la columna y la FK `voice_agent_config_id` (contrato de datos y API).
- Se eliminó la `relationship("TenantVoiceAgentConfig")` del ORM de Agent Builder. La validación de draft y el compilador leen `voice_legacy.public.VoiceLegacyFacade.get_voice_agent_defaults` → `LegacyVoiceDefaults{config_id, tenant_id, default_voice, voice_provider}` (valida existencia y tenant; nunca ORM).
- El puente sigue intacto: si falta `realtime.voice` y hay `default_voice`, el compilador genera el mismo `realtime.voice` y el puente `realtime.settings.voice`. El proveedor de ese puente (`"ultravox"`) lo declara Voice Legacy, no Agent Builder.
- Pendiente (no en esta fase): backfill opcional de `realtime.voice` y retiro del puente tras el smoke manual de agentes antiguos.

#### Pendiente para la siguiente fase

- Voice Orchestration: mover `voice_session_service` & co. a `app/modules/voice/`, y con él el registro de proveedores y los adapters bajo `voice_providers`.
- `RuntimeSessionSpecV1` sigue en `app/schemas/runtime_session.py` como contrato compartido (no se movió para no tocar el trust boundary del runtime).
- `IntegrationEventService` sigue como auditoría compartida (allowlist).

### 3. Voice Orchestration — hecho

Estructura: `app/modules/voice/{domain/{errors,lifecycle,session_context,runtime_contracts,views}.py, application/{session_service,context_resolution,runtime_dispatcher,runtime_events,facade,ports}.py, infrastructure/{models,livekit_runtime}.py, api/{router,schemas}.py, public.py, wiring.py}`.

- **Ownership**: `voice_sessions`, `voice_session_events` (ORM en `infrastructure/models.py`, registrado en `app/models/__init__.py`; mismas tablas, FKs, índices y constraints; sin migración). Lifecycle (máquina de estados en `domain/lifecycle.py`, idéntica), creación idempotente, snapshot y enriquecimiento monotónico de `SessionContextV1`, dispatch al runtime, LiveKit room dispatch/cleanup (`infrastructure/livekit_runtime.py`), ingesta de eventos del runtime (`application/runtime_events.py`), spec del runtime, token WebRTC y orquestación del endpoint de tools.
- **Contratos**: `SessionContextV1` (`domain/session_context.py`) y `RuntimeSessionSpecV1` (`domain/runtime_contracts.py`) movidos sin cambiar su forma serializada. `voice.public` sigue el patrón de `agents.public`: al importarse sólo carga contratos, vistas y errores (test `test_public_apis_import_light`), por eso el compilador de Agent Builder importa `RuntimeSessionSpecV1` desde `voice.public` sin ciclos.
- **API pública** (`voice.public`): `VoiceSessionFacade.get_tool_session`, `record_event`, `enrich_context`, `release_sessions_of_deleted_agent`, `get_projection_facts`; DTOs `ToolSessionView`, `SessionProjectionFacts`, `SessionEventFact`; contratos y errores. Ningún método devuelve `VoiceSession`/`VoiceSessionEvent`. No se añadieron `create_session`/`dispatch_session`: no tienen consumidor fuera de Voice.
- **Puertos** (`application/ports.py`): `CrmContextPort` (snapshots `ContactSnapshot`/`LeadSnapshot` de `crm.public`; Voice construye `ContactContext`/`LeadContext`/`CampaignContext`) y `VoiceProjectionPort` (`analytics.public.VoiceCallProjectionFacade`). Enlazados en `wiring.py`.
- **Salientes** (sólo `public.py`): `agents` (agente publicado, estado, bindings, compilación), `crm` (snapshots), `tools` (invocación), `voice_providers` (registro, credenciales), `telephony` (normalización de teléfono, dial SIP QA), `analytics` (proyección), `identity` (`VOICE_RUNTIME_V2`). Shared: `api.auth.deps`, `core.config`, `db.*`, `security.voice_runtime_auth`.
- **Router `voice_runtime`** (`api/router.py`, mismas URLs): sesiones, preview de contexto, eventos de QA, token WebRTC, spec y eventos del runtime son de Voice; la credencial la resuelve `voice_providers.public` (tenant derivado de la sesión, provider validado contra la sesión); la invocación de tools delega en `tools.public`; el dial SIP QA en `telephony.public`; la proyección y el estado de `CrmVoiceCall` en `analytics.public`.
- **Proyección**: `VoiceCallProjectionService` (legacy, Analytics/CRM) consume `SessionProjectionFacts` en lugar del ORM de Voice y absorbe la actualización de estado de `CrmVoiceCall` que vivía en el endpoint. Voice no importa `app.models.crm` ni `app.models.analytics`.
- **No migrado a propósito**: Voice Experiences, Voice Legacy y sus webhooks (`/webhook/{provider}`, `/events` de Ultravox, `voice_runtime_webhook_service` → `TenantVoiceRuntimeCall`: son del flujo Ultravox directo/Voice Experiences, no de `VoiceSession`). Telephony se migró después (ver §4).
- **Shims**: los 4 (`app.models.voice_sessions`, `app.services.voice_session_service`, `app.services.livekit_runtime_backend`, `app.services.voice_runtime_dispatcher`) se **eliminaron** al migrar Telephony (cero consumidores). `KNOWN_SHIMS` en `test_module_boundaries.py` está vacío; un shim nuevo debe registrarse ahí y en esta hoja de ruta.
- **Pendiente**: la componente conexa Agents ↔ Tools ↔ Voice ↔ Analytics (sólo vía `public.py`/wiring) creció al pasar la proyección detrás de `analytics.public`; se reducirá cuando la proyección se dispare por eventos (`voice.session.*`) al migrar CRM/Analytics.

### Voice Providers — frontera consolidada

Estructura: `app/modules/voice_providers/{domain/{registry,contracts,errors}.py, application/{service,ports}.py, infrastructure/{adapters,ultravox,credentials}.py, public.py}`.

- `app/domain/voice_registry.py` → `domain/registry.py` (catálogo de proveedores, modelos, capacidades, parámetros y compatibilidad de voz). Agent Builder, Voice y las APIs usan `voice_providers.public`.
- `VoiceProviderAdapter` (puerto) + registro de adapters (`infrastructure/adapters.py`); `UltravoxProviderAdapter` es el único archivo que conoce `UltravoxProviderError` y lo traduce a `VoiceProviderError(code, remote=True, reason)`. `public.py`, `application` y `domain` no conocen ningún proveedor concreto (test).
- Credenciales del runtime: `VoiceProviderFacade.resolve_runtime_credential(tenant_id, provider)` sobre `TenantVoiceProviderConfig` (cifrado, agnóstico de proveedor). El endpoint interno no cambia y conserva el trust boundary: Voice resuelve la `VoiceSession` por `session_id`, deriva el tenant y valida el provider antes de pedir la credencial.
- El workspace de administración Ultravox (`/integrations/voice/providers/{provider}/...`) sigue usando `UltravoxAdminService` vía `voice_provider_admin`; su `_error` mapea igual `UltravoxProviderError` y `VoiceProviderError(remote=True)`.
- Pendiente: mover físicamente `UltravoxAdminService`/`ultravox_provider_client`/`voice_config_service` bajo `voice_providers/infrastructure` cuando se retire Voice Legacy (hoy también los usa el flujo legacy).

### 4. Telephony — hecho

Estructura: `app/modules/telephony/{domain/{errors,phone_numbers,routes,capacity,views}.py, application/{ports,route_service,capacity_service,dial_service,outbound_service,provisioning_service}.py, infrastructure/{models,livekit_sip,asterisk_agent}.py, api/{router,schemas}.py, public.py, wiring.py}`.

- **Ownership**: `tenant_sip_routes` (`TenantSipRoute`, misma tabla/constraints, sin migración); configuración, credenciales (cifradas), PBX, caller id, países y `max_concurrent_calls` de la ruta; provisioning Asterisk (endpoints internos del agente, mismas URLs) y trunk SIP de LiveKit; marcación del participante SIP; mapeo de estados SIP (486→`busy`; 603/607/608→`rejected`; 408/480/487→`no_answer`; otro→`failed`); normalización de teléfonos (`normalize_caller_id`, `normalize_outbound_phone`, `SUPPORTED_OUTBOUND_COUNTRIES`, `VoicePhoneValidationError`); política de capacidad. **No** es dueño de `VoiceSession`, Agent Builder, `CrmLead`, `CrmVoiceCall`, `Call` de Analytics, Voice Legacy ni Voice Experiences.
- **Descomposición de `OutboundVoiceCallService`**: pasó a ser un adaptador CRM delgado (traduce `VoiceCallActionRequest/Response`). El registro CRM vive en `crm.public.OutboundCallLedger` (valida lead/contacto, abre/actualiza `CrmVoiceCall`, DTOs `OutboundContactRef`/`CallState`); el caso de uso es `telephony.public.TelephonyFacade.place_outbound_call(command, ledger)`; el ciclo de vida de la sesión y el dispatch al runtime los ejecuta Voice (`voice.public.VoiceTelephonyFacade`).
- **Orden preservado**: validar sesión SIP → resolver y bloquear ruta (`SELECT … FOR UPDATE`) → capacidad → vincular ruta/trunk → `voice.outbound.requested` → dispatch del runtime (vía Voice) → esperar `runtime_ready` (`LIVEKIT_SIP_RUNTIME_READY_TIMEOUT_SECONDS`; terminales failed/ended/cancelled) → crear participante SIP → `voice.sip.dial.started` → answered/error → limpieza del room en fallo. Idempotencia: mismo tenant + `idempotency_key` ⇒ una `VoiceSession`, un `CrmVoiceCall`, una llamada SIP.
- **Puertos** (`application/ports.py`, enlazados en `wiring.py`): `VoiceTelephonyPort` (→ `voice.public`), `SipTransportPort` (→ `LiveKitSipService`), `CallLoadPort` (→ `crm.public`, conteo de llamadas legacy en vuelo), `CallProjectionPort` (→ `analytics.public`), `OutboundCallLedger` (→ `crm.public`). La configuración del proveedor entra como DTO (`voice_providers.public.ProviderConfigRef`), nunca ORM; los flags vienen de `identity.public`.
- **Capacidad**: dos fuentes preservadas (sesiones SIP activas de Voice vía `count_active_telephony_sessions`, y llamadas legacy `starting,queued,ringing,in_progress` vía `CallLoadPort`). La aplicación (`CapacityService`) está separada del reporte del dashboard (`services/voice_capacity_report_service.py`).
- **API pública** (`telephony.public`): `TelephonyFacade` (`place_outbound_call`, `dial_qa_session`), `SipRouteFacade` (`get_route`, `get_active_route`, `lock_route`, `get_connection`, `upsert`, `sync_livekit_trunk`), `CapacityFacade` (`callbacks_in_flight`, `record_capacity_reached`, `record_release`), `run_asterisk_provisioner_agent`; DTOs `SipRouteView`, `SipRouteConnection`, `SipRouteSettings`, `PlaceOutboundCallCommand`, `OutboundCallResult`; reexporta normalización de teléfonos y errores. Al importarse sólo carga contratos (test `test_public_apis_import_light`).
- **Agente del PBX**: `python -m app.workers.asterisk_provisioner` se conserva como lanzador de una línea hacia `infrastructure/asterisk_agent.py`; sigue usando sólo la librería estándar. El unit systemd no cambia.
- **Dependencias**: Telephony no importa internals de Voice/CRM/Analytics/Voice Providers/Integrations/Identity (sólo `<módulo>.public`) ni `app.models.voice_sessions`/`app.models.crm`; `domain/` es puro (sin SQLAlchemy/FastAPI/LiveKit/httpx). `VoiceProviderConfigStore` (`services/voice_provider_config_store.py`) se separó de `VoiceConfigService` para que el adapter de proveedor no arrastre a Telephony (evita un ciclo).
- **Retirado**: los 4 shims de Voice, `voice_phone_service`, `livekit_sip_service`, `voice_sip_route_service`, `voice_capacity_service`, `voice_session_sip_service`, `asterisk_provisioning_service`, `schemas/asterisk_provisioning`, `api/endpoints/asterisk_provisioning`. `voice_call_service` (legacy) y `scripts/backfill_voice_session_calls.py` ya no importan el ORM de Voice.
- **Corrección de concurrencia** (hallada con PostgreSQL real): `VoiceSessionService.create` capturaba `IntegrityError` sólo en `commit`, pero el índice único `(tenant_id, idempotency_key)` también dispara en `flush`; y `lock_session` leía una fila obsoleta del identity map tras esperar el lock (doble marcación posible). Ambas corregidas (`populate_existing`).
- **Pruebas**: unitarias de dominio (`test_telephony_domain.py`), integración con fakes/SQLite (`test_outbound_voice_call_service.py`, `test_livekit_sip_service.py`, `test_asterisk_provisioning.py`, …), arquitectura (`test_module_boundaries.py`) y **PostgreSQL real** (`test_telephony_postgres.py`: misma idempotency key en paralelo, `max_concurrent_calls`, lock de la ruta). **No existe E2E SIP real** (requiere LiveKit + PBX + ruta + credenciales del proveedor): sigue pendiente de verificación manual en staging.

### 5. Scheduling — hecho

Estructura: `app/modules/scheduling/{domain/{booking,contracts,errors,dates}.py, application/{booking_service,availability_service,config_service,resource_service,booking_config_service,provider_resolver,ports,views,google_admin,integration_admin,calcom_webhook,voice_booking,booking_history}.py, infrastructure/{models.py,google/{calendar,oauth,admin,adapter}.py,calcom/{client,availability,sync,admin,adapter,constants}.py}, api/{router,integrations_router,calcom_router,schemas}.py, public.py, wiring.py}`.

- **Ownership** (ORM en `infrastructure/models.py`, mismas tablas/FKs/índices/constraints; DDL de las 78 tablas verificado idéntico a `develop`, una sola head de Alembic): `tenant_booking_configs`, `tenant_voice_booking_configs`, `tenant_google_calendar_connections`, `tenant_google_calendars`, `tenant_scheduling_{configs,resources,resource_calendars,teams,team_members,exceptions,schedules,event_types,provider_objects}`, `tenant_agent_scheduling_configs` y **`crm_bookings`/`crm_booking_events`** (el nombre físico no determina el bounded context; `CrmBooking` ya no declara relaciones ORM a `CrmLead`/`CrmContact`, las FKs a nivel DB se mantienen).
- **Sin shims ni reexports**: se midieron los consumidores y se reescribieron todos (app, tests, scripts); `KNOWN_SHIMS` sigue vacío.
- **Frontera con CRM**: `BookingCustomerPort` (lead → `BookingCustomer`) y `CrmActivityPort` (timeline) se enlazan en `wiring.py` a `crm.public` (`CrmFacade.get_lead/get_contact/record_activity`, ahora con `record_activity`); el comando de reserva es `CreateBookingCommand` (dataclass propio) y el endpoint CRM `POST /crm/leads/{id}/bookings` quedó como adaptador HTTP de `SchedulingFacade.create_booking`. Scheduling ya no importa `CrmLead`, `CrmContact`, `CrmActivityService` ni `app.schemas.crm`.
- **Frontera con Notifications**: `BookingEventPublisherPort.publish_booking_event` anuncia `booking.created|cancelled|rescheduled` y nunca propaga errores al flujo. El adaptador (`wiring.NotificationBookingEvents`) usa la infraestructura existente de eventos de dominio (`NotificationEventPipeline` → `domain_events`, con las mismas claves de idempotencia `booking:{id}:created|cancelled|rescheduled:{digest}`). **Es el único puente temporal**: `scheduling.wiring → services.notification_event_pipeline` (allowlist explícita); se retira cuando Notifications se suscriba a `domain_events` por sí misma. El pipeline, a su vez, ya no lee `CrmBooking`: obtiene un `BookingView` de `scheduling.public` (sólo la clave `notification_custom` de la metadata).
- **API pública** (`scheduling.public`; carga sólo contratos y errores, casos de uso perezosos): `SchedulingFacade` — `is_booking_configured`, `get_available_slots`, `create_lead_booking` (variante Tool Platform: `notes: str | None`, valida con pydantic), `create_booking`, `list_lead_bookings`, `get_booking`, `cancel_booking`, `reschedule_booking`, `detach_customers`, `find_voice_booking_config_id`, `get_booking_config`, `configure_calcom`, `test_calcom`, `list_google_connections`, `delete_google_connection`, `catalog_status_inputs`. DTOs: `BookingView`, `BookingSummary`, `BookingCustomer`, `CreateBookingCommand` + contratos HTTP (`BookingConfig*`, `GoogleCalendarConnectionResponse`, …). Ninguno devuelve ORM, tokens OAuth ni claves de Cal.com. Errores neutros (`SchedulingError`, `BookingNotFoundError`, `BookingCustomerNotFoundError`, …) subclases de `ValueError` para conservar mensajes y status HTTP.
- **Routers** (mismas URLs/roles/payloads; OpenAPI de las 257 rutas verificado idéntico a `develop` con refs expandidos): `/api/v1/scheduling/*` (`api/router.py`), `/api/v1/integrations/{booking,calcom,google-calendar,scheduling}/*` (`api/integrations_router.py`, antes dentro de `integrations.py`) y `/api/v1/{availability,bookings,calcom/webhook}` (`api/calcom_router.py`). Ningún router importa el ORM: serialización en `application/views.py` y `google_admin.py`. El webhook de Cal.com solo autentica y delega la reconciliación a `reconcile_calcom_webhook`.
- **Adapters internos**: Google Calendar (`infrastructure/google/`) y Cal.com (`infrastructure/calcom/`) viven dentro del módulo (no hay `scheduling_providers`). `domain/` es puro (reglas de proveedor, payload de Cal.com, mapeo de estados, fechas).
- **Transacciones**: sin cambios (el booking `pending` se confirma *antes* de llamar al proveedor; ninguna llamada externa mantiene locks). Sin reintentos nuevos.
- **Corrección de concurrencia** (probada primero sobre PostgreSQL real, 3/3 fallos): `select_resource_round_robin` entregaba el **mismo recurso a dos reservas simultáneas** y podía perder incrementos de `total_assigned_count`. Se resolvió en dos fases para **no mantener locks de fila durante I/O de red**: (1) *disponibilidad* (`_find_available_candidates`: horario, excepciones y Google FreeBusy) sin ningún `FOR UPDATE`, que produce los ids disponibles; (2) *asignación atómica* (`_allocate_candidate_atomically`): `SELECT … FOR UPDATE` sólo de los candidatos disponibles en orden de id (sin deadlocks), relectura fresca con `populate_existing`, re-ranking post-lock (`priority DESC, last_assigned_at ASC NULLS FIRST, total_assigned_count ASC, created_at, id`), incremento de contador y `COMMIT` — milisegundos, sin red. Se revalidan tenant/activo/pertenencia al equipo localmente tras el lock. Contrapartida asumida: FreeBusy se evalúa para todos los candidatos (antes se detenía en el primero libre), porque el ganador final lo decide el ranking post-lock. No se usa `SKIP LOCKED` (alteraría la justicia del reparto). Pruebas: `test_scheduling_postgres` (FreeBusy sin locks vía `FOR UPDATE NOWAIT`, FreeBusy lento que no bloquea otra asignación, ranking post-lock con vista previa obsoleta) y guarda estructural en `test_scheduling_boundaries`.
- **Hardening de consistencia (2026-10-03)**: `domain/operations.py` (tipos, estados, normalización de clave, fingerprints, clasificación de resultado incierto) y `domain/booking.py` (`SLOT_BLOCKING_STATUSES`, `intervals_overlap`) son puros; `application/operation_service.py` y `application/slot_guard.py` orquestan idempotencia y guarda de slot; `BookingService` los usa en create/cancel/reschedule. Errores neutrales nuevos (subclases de `ValueError`): `SlotConflictError`, `IdempotencyConflictError`, `BookingOperationInProgressError`. Frontera intacta: Tools sólo pasa `idempotency_key` a `scheduling.public`; Scheduling no conoce `VoiceSession`. Detalle y garantías en `docs/ARCHITECTURE.md`.
- **Hardening final PR #121 (2026-10-04)**: Identidad de la llamada de herramienta: el voice-runtime toma `FunctionCall.call_id` de LiveKit (inyectado por tipo como `RunContext`, nunca parte del `input_schema` visible al LLM; si no cabe en `[A-Za-z0-9._-]{1,64}` se normaliza con un digest determinista `lk-<sha256>`; sin `call_id` falla cerrado) y lo envía como `invocation_id` → Tools lo convierte en `voice:{session_id}:{call_id}` → idempotencia de operaciones de booking en Scheduling. Un intento HTTP nuevo de la misma llamada lógica produce la misma clave; llamadas distintas, claves distintas. `invoke_tool` sigue siendo un único intento HTTP (sin retry automático) y las custom tools no heredan esta garantía. Cancelación en Google: el error de `delete_event` ya no se absorbe; se propaga con su cadena causal y, si es de transporte (timeout/conexión), la operación queda `provider_unknown` sin marcar el booking como cancelado localmente, sin publicar `booking.cancelled`, sin actividad de timeline y sin reintento ciego. **Deuda conocida (fuera del PR #121)**: (A) *Scheduling Provider Outcome Classification*: hoy `is_outcome_unknown` clasifica por tipo/nombre de excepción (timeouts, conexión) en lógica de dominio; algunos HTTP 5xx recibidos tras enviar la petición siguen tratándose como fallo definitivo aunque su resultado sea desconocido. Objetivo: que los adapters clasifiquen (`ProviderDefinitiveFailure` para 400/401/403/404/409 conocidos vs `ProviderOutcomeUnknown` para timeouts, resets y ciertos 5xx, según el contrato de Google/Cal.com) en lugar de crecer listas de strings. (B) *Provider Unknown Reconciliation*: las operaciones `provider_unknown` quedan congeladas a propósito (booking `pending`/tentativo, slot bloqueado, sin reintento). Un reconciler futuro consultará el estado remoto (create: `provider_booking_id/uid`, metadata y correlación; cancel: evento inexistente/cancelado; reschedule: fecha remota = destino o = origen) y completará la operación, permitirá un reintento seguro o la dejará incierta. Sin cron/worker/endpoint en este cambio. **Garantías que aún no existen**: no hay exactly-once frente a Google/Cal.com, la clasificación de 5xx es incompleta y no hay reconciliación.
- **Deuda conocida (no introducida ni corregida aquí)**: no hay idempotencia de creación de reservas ni restricción local contra doble reserva del mismo recurso/slot (sólo FreeBusy de Google); cancelar dos veces llama dos veces al proveedor.
- **Pruebas**: `test_scheduling_domain.py`, `test_scheduling_boundaries.py` (fakes + SQLite), `test_scheduling_postgres.py` (PostgreSQL real: Round Robin, ciclo de vida, doble cancelación) y reglas AST en `test_module_boundaries.py` (mutation-checked). **No existe E2E real de Google Calendar ni de Cal.com** (requieren cuentas/credenciales): pendiente de smoke manual en staging.

### 6. CRM

- **Ownership**: `crm_contacts`, `crm_leads`, `crm_pipeline_stages`, `crm_activities`, `crm_tasks`, `crm_call_contexts`, `crm_voice_calls*`.
- **Entrantes**: casi todos (Voice, Voice Legacy, Scheduling, Integrations, Telephony, Tools). Scheduling ya consume `crm.public` (cliente de la reserva y timeline).
- **Salientes**: Integrations (email, WhatsApp), Scheduling, Telephony, Voice Legacy, Billing/Analytics.
- **API pública**: `CrmFacade` (existe: `get_or_create_open_lead -> (ContactRef, LeadRef)`), `find_contact_by_phone`, `get_lead`, `record_activity`, handlers de eventos (`voice.session.completed`, `booking.*`, `message.sent`).
- **Imports a eliminar**: todos los accesos directos a `models.crm` desde otros dominios (~40).
- **Riesgos**: es el módulo con más consumidores; migrar sus lecturas primero (query services), luego escrituras por eventos in-process sobre `domain_events` existente.

### 7. Notifications

- **Ownership**: `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events`, `notification_deliveries`.
- **Entrantes**: Scheduling y Voice (pipeline), Integrations (`whatsapp_message_service → NotificationDeliveryStatusService`).
- **Salientes**: Integrations (WhatsApp client/message/templates, Chatwoot, Meta).
- **API pública**: `publish_event(...)` (pipeline), `report_delivery_status(...)`.
- **Imports a eliminar**: `notification_* → whatsapp_client` (→ `integrations.public`), y el inverso `whatsapp_message_service → models.notifications`.
- **Riesgos**: worker con lease/claims; `test_notification_worker_postgres` sólo con PostgreSQL de pruebas.

### 8. Integrations / Messaging

- **Ownership**: WhatsApp, Email, Chatwoot, `tenant_integrations`; `crm_whatsapp_messages` (lógico).
- **Entrantes**: CRM, Notifications, Tools, Agents, Identity (admin), Voice (handoff).
- **Salientes**: CRM (actividades), Notifications (delivery status), Voice Experiences (context schemas para Flows).
- **API pública**: `WhatsAppFacade` (existe: `get_approved_template_contract`, `send_template`), `EmailFacade.send`, `is_configured(kind)`.
- **Riesgos**: Resend, Email Composer, MinIO/S3, Chatwoot multi-tenant. Considerar separar `messaging/` (canales) de `integrations/` (catálogo + credenciales).

### 9. Identity / Tenancy

- **Ownership**: `tenants`, `users`, `tenant_memberships`, `access_audit_logs`, `tenant_feature_grants`.
- **API pública**: `FeatureFlags.is_enabled/require_enabled`, `FeatureDisabledError`, constantes de feature (existe, mínima); pendientes `AuthContext`, `require_roles`.
- **Riesgos**: no romper Auth0. Muchos consumidores, poco riesgo lógico; migración mayormente mecánica.

### 10. Billing y 11. Analytics

- **Billing**: `tenant_billing_plans`, `tenant_usage_alerts`, `external_provider_pricing`. API: `provision_plan`, `usage_summary`. Eliminar `onboarding_service → models.billing`.
- **Analytics**: `calls`, `call_events`, `metric_snapshots_daily`. Alimentar `calls` por evento de sesión en vez de que Voice y Voice Legacy escriban la tabla.

## Eventos entre módulos

Reutilizar `domain_events` + `NotificationEventPipeline` (idempotente, persistente) y, cuando no haga falta persistencia, llamadas síncronas a `public.py`. No introducir Kafka/RabbitMQ ni un bus nuevo. Candidatos: `voice.session.completed` → CRM projection, Analytics, Billing; `booking.created/cancelled` → CRM timeline, Notifications; `message.sent/delivered` → CRM timeline, Notifications.

## Preparación para nuevas capacidades

Workflow Automation, Knowledge, Human Handoff, Agent Copilot, Evaluations y Observability nacen directamente como `app/modules/<m>/` con `public.py` y tests de frontera; nunca añaden archivos a `app/services/`. Un nuevo proveedor de voz es un adapter detrás de las abstracciones existentes (`voice_registry`, `RealtimeProviderFactory`), no un módulo.

## Casos límite documentados (datos inválidos, no contratos)

- Una plantilla WhatsApp `approved` con parámetros internamente malformados falla al construir `WhatsAppTemplateContract`, antes de validar `recipient.strategy` (`test_platform_tool_contract_service.test_malformed_approved_template_fails_while_building_its_contract`).
- Un binding de tool con `config` no-dict se normaliza a `{}` en la vista de lectura, aunque el schema del draft ya rechaza ese estado (`test_agent_builder_provider_agnostic.ToolBindingViewTests`).
