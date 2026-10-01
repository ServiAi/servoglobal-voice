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
| 3 | Voice Orchestration | Alta | **Siguiente** |
| 4 | Telephony | Media-alta | |
| 5 | Scheduling | Alta | |
| 6 | CRM | Alta | |
| 7 | Notifications | Media | |
| 8 | Integrations / Messaging | Alta | |
| 9 | Identity / Tenancy | Media (muchos consumidores, poca lógica) | |
| 10 | Billing | Baja | |
| 11 | Analytics | Media | |
| — | Voice Experiences | Media | Tras Telephony |
| — | Voice Providers | Media | Frontera creada (`voice_providers.public`); mover registro + adapters al migrar Voice |
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

### 3. Voice Orchestration

- **Ownership**: `voice_sessions`, `voice_session_events`, `tenant_voice_provider_configs` (traer desde Voice Legacy).
- **Entrantes**: Tools, Telephony (outbound, SIP QA), Agents, Voice Experiences (webhooks), endpoints `voice`/`voice_runtime`.
- **Salientes**: Agents, CRM (resolución de contexto, proyección), Telephony (SIP QA desde el endpoint), Voice Legacy (`voice_config_service`, `ultravox_ingestion_service`), Integrations (Chatwoot handoff), Billing/Analytics (`analytics.Call`).
- **API pública propuesta**: `VoiceSessionFacade` (existe: `get_tool_session`, `record_event`, `enrich_context` por id con `ContactRef`/`LeadRef`, `release_sessions_of_deleted_agent`), `ToolSessionView` (existe), `create_session`, `dispatch`, `close_sessions_for_agent`, `SessionContextV1`, `RuntimeSessionSpecV1`, `resolve_runtime_credential`.
- **Ya resuelto en la migración de Agent Builder**: Voice ya no importa modelos ni servicios de Agents (`lock_published_agent`, `get_agent_status`, `compile_runtime_spec`, `describe_agent`, `agent_names` vía `agents.public`) y `VoiceSession` ya no tiene relaciones ORM hacia `TenantAgent`/`TenantAgentVersion`.
- **Imports a eliminar**: `contact_resolution_service → models.crm` (→ `crm.public` query), `voice_call_projection_service → models.crm/analytics` (→ evento `voice.session.completed` consumido por CRM y Analytics), `voice_runtime → voice_config_service` (mover al módulo).
- **Riesgos**: altos. Es el trust boundary con `voice-runtime`; **no cambiar** `RuntimeSessionSpecV1`, `SessionContextV1`, rutas internas, JWT del runtime ni el resolver de credenciales. `voice-runtime/` sigue sin DB.

### 4. Telephony

- **Ownership**: `tenant_sip_routes`; caso de uso outbound.
- **Entrantes**: CRM (`crm_voice` endpoint, métricas de capacidad), Voice (SIP QA), Voice Experiences (rutas, teléfonos).
- **Salientes**: Voice (session, dispatcher, projection, LiveKit backend), CRM (`CrmLead`, `CrmVoiceCall`), Voice Legacy/Experiences (callbacks).
- **API pública propuesta**: `place_outbound_call(...) -> voice_session_id`, `normalize_phone`, `capacity_snapshot(tenant_id)`, `get_route(tenant_id)`.
- **Imports a eliminar**: `outbound_voice_call_service → models.crm` (CRM crea `CrmVoiceCall`), `voice_capacity_service → models.crm`.
- **Riesgos**: `outbound_voice_call_service` depende del orden estricto dispatch → `voice.agent.ready` → participante SIP; mover sin tocar la secuencia. Pruebas actuales son con fakes: no hay E2E real.

### 5. Scheduling

- **Ownership**: tablas `tenant_scheduling_*`, `tenant_booking_configs`, `tenant_google_*`, `tenant_voice_booking_configs`, `tenant_agent_scheduling_configs`, `crm_bookings`/`crm_booking_events` (lógico).
- **Entrantes**: CRM (endpoint), Tools (`scheduling.public`), Agents (preflight), Voice booking tools legacy.
- **Salientes**: CRM (`CrmLead`, `CrmActivity`), Notifications (`NotificationEventPipeline`), Integrations (eventos, config).
- **API pública**: `SchedulingFacade` (existe: `get_available_slots`, `create_lead_booking`), `is_configured`, `cancel/reschedule`.
- **Imports a eliminar**: `booking_service → crm_activity_service` (evento `booking.created`), `booking_service → models.crm.CrmLead` (→ `crm.public.get_lead`).
- **Riesgos**: no romper Cal.com (webhook de reconciliación), Google Calendar foundation ni voice booking tools. Partir `models/integrations.py` requiere que la clase se reexporte desde el archivo viejo hasta migrar los importadores.

### 6. CRM

- **Ownership**: `crm_contacts`, `crm_leads`, `crm_pipeline_stages`, `crm_activities`, `crm_tasks`, `crm_call_contexts`, `crm_voice_calls*`.
- **Entrantes**: casi todos (Voice, Voice Legacy, Scheduling, Integrations, Telephony, Tools).
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
