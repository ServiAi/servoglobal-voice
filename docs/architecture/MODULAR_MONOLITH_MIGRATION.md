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

Retiro de shims: cuando `grep -r "app.services.<legacy>" backend/` sólo encuentre tests, migrar los `patch(...)` de esos tests a la ruta nueva; borrar el shim en el PR siguiente, para no romper ramas paralelas que todavía importen la ruta vieja.

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
| 2 | Agent Builder | Media | Siguiente |
| 3 | Voice Orchestration | Alta | |
| 4 | Telephony | Media-alta | |
| 5 | Scheduling | Alta | |
| 6 | CRM | Alta | |
| 7 | Notifications | Media | |
| 8 | Integrations / Messaging | Alta | |
| 9 | Identity / Tenancy | Media (muchos consumidores, poca lógica) | |
| 10 | Billing | Baja | |
| 11 | Analytics | Media | |
| — | Voice Experiences | Media | Tras Telephony |
| — | Voice Legacy | — | **No migrar**: aislar tras `voice_legacy.public` y retirar cuando `voice_runtime_v2` sea el único camino |

### 1. Tool Platform — hecho (patrón de referencia)

- **Ownership**: `tenant_tools`, `tenant_http_tool_configs`, `tenant_tool_credentials`; schema de `runtime_binding_json["tools"][].config`.
- **Entrantes**: Agent Builder (`agent_service`, `agent_compiler_service`), Voice (`api/endpoints/voice_runtime.py`), `main.py` (router).
- **Salientes** (sólo `public.py`): `voice` (`ToolSessionView`, `VoiceSessionFacade.get_tool_session/record_event/enrich_context`), `crm` (`ContactRef`, `LeadRef`, `CrmFacade`), `scheduling` (`BookingSummary`), `integrations` (`WhatsAppTemplateContract`, `WhatsAppSendOutcome`), `agents` (bool), `identity` (`FeatureFlags`). Shared kernel: `integration_event_service`, `secret_manager_service`, `api.auth.deps`, `core.config`, `db.*`.
- **API pública**: `ToolDispatchService`, errores `Tool*Error`, `ToolResolverService`, `ToolCatalogService`, `PlatformToolContractService`/`Error`, `ResolvedToolDefinition`, `get_tool`, `from_platform`, `ToolRegistryValidationError`, `is_custom_tool_credential_ready`.
- **Frontera de datos (hardening, 2026-10-01)**: ningún ORM de otro módulo entra en Tools (antes `VoiceSession` + `TenantAgent`/`TenantAgentVersion` por relación, `CrmContact`, `CrmLead`, `TenantWhatsAppTemplate` oculto en `_row`). `ToolPorts` no usa `Any` para entidades. El enriquecimiento monotónico de `SessionContextV1` sigue siendo responsabilidad exclusiva de Voice (`VoiceSessionService.enrich_context_by_ids` recarga las filas por id y aplica las mismas reglas y códigos).
- **Shims**: los 18 siguen en su sitio, pero **no queda ningún consumidor** en código de producción, tests, scripts ni migraciones (`git grep` sobre las rutas legacy sólo encuentra el mapeo de `test_module_boundaries.py`). Borrarlos al inicio del sprint de Agent Builder, una vez fusionadas las ramas paralelas.
- **Excepciones de arquitectura restantes**: allowlist de shared kernel (`api.auth.deps`, `core.config`, `db.base`, `db.mixins`, `db.session`, `integration_event_service`, `secret_manager_service`); `notes: Any` en `SchedulingToolPort.create_lead_booking` (texto libre del LLM); `voice.public` en la capa `domain` (`SessionContextV1` es parte del contrato de invocación).

### 2. Agent Builder

- **Ownership**: `tenant_agents`, `tenant_agent_versions`.
- **Entrantes**: Voice (`voice_runtime` → compiler; `voice_session_service`/projection → modelos), Voice Legacy (`ultravox_admin_service` → `agent_service`, `voice_selection_service`, `schemas.agents`), Tools (`agents.public`).
- **Salientes**: Tools (ya `public`), Voice (`voice_session_service`, `livekit_runtime_backend`, `models.voice_sessions`), Voice Legacy (`ultravox_admin_service`, `ultravox_provider_client`), Scheduling (`booking_service`), Integrations (`whatsapp_config_service`, `models.integrations`).
- **API pública propuesta**: `AgentsFacade.get_published_version(tenant_id, agent_id)`, `compile_runtime_spec(session)`, `is_tool_bound_to_published_version` (existe), schemas `AgentVoiceConfig`/`AgentToolBinding`.
- **Imports a eliminar**: `voice_runtime → agent_compiler_service`; `voice_session_service → models.agents`; `agent_service → booking_service/whatsapp_config_service` (→ `is_configured` en cada `public.py`); `agent_service → voice_session_service/livekit_runtime_backend` (→ `voice.public.close_sessions_for_agent`).
- **Riesgos**: no reintroducir dependencia directa a Ultravox en el dominio del agente; `AgentService` es el servicio con más dependencias salientes del backend.

#### Ciclo `AgentService ↔ UltravoxAdminService` (a eliminar en esta fase)

Estado real del código:

```text
AgentService.publish()                       (provider_managed)
    -> UltravoxAdminService.validate_execution_preflight(tenant, provider_agent_id)
AgentService._publish_voice_preflight()     (serviglobal_managed)
    -> UltravoxAdminService.get_voice(...) / validate_external_voice_credentials(...)
AgentService._validate_provider_agent_link()
    -> UltravoxAdminService.validate_provider_agent_link(...)
UltravoxAdminService.import_agent()
    -> AgentService.create_agent(...) + escribe realtime.provider_extensions del draft
```

Hoy se sostiene con imports perezosos dentro de funciones en ambos lados. Diseño objetivo:

```text
Agent Builder (app.modules.agents)
   application/ports.py: VoiceProviderPort (Protocol)
        validate_voice(tenant_id, AgentVoiceConfig) -> None | VoiceProviderError(code)
        validate_provider_agent(tenant_id, provider, agent_ref) -> ProviderAgentSnapshot (DTO)
   wiring.py -> voice.public.VoiceProviderFacade
                     |
                     v
Voice (provider registry: voice_registry + voice_provider_admin._ADAPTERS)
                     |
                     v
UltravoxAdminService (adapter, Voice Legacy) -> Ultravox API
```

1. `VoiceProviderPort` vive en Agent Builder y sólo expone lo que el preflight necesita, con DTOs (`ProviderAgentSnapshot{agent_id, revision_id, tools: tuple[ProviderToolRef]}`) y códigos de error estables (`voice_not_accessible`, `provider_resource_not_found`...), nunca `UltravoxProviderError`.
2. `voice.public.VoiceProviderFacade` despacha por `provider` usando el registro ya existente (`voice_provider_admin.get_provider_admin_service`), de modo que un segundo proveedor no toca Agent Builder.
3. **La importación se invierte**: `import_agent` deja de llamar a `AgentService`. El adapter devuelve un `ProviderAgentImport` (DTO: nombre, idioma, system prompt, revisión, tools clasificadas) y es **Agent Builder** quien crea el agente (`AgentsFacade.import_provider_agent(tenant_id, provider, agent_ref)`), escribiendo él mismo `provider_extensions`. El endpoint de importación pasa a llamar a Agent Builder.
4. Resultado: `agents → voice.public` y ninguna arista `voice/ultravox → agents` salvo `agents.public`; el test de fronteras prohíbe `app.services.ultravox_*` desde `app.modules.agents`.
5. Compatibilidad: mismos códigos de error de publish (`voice_not_accessible`, `tool_integration_not_configured`...), mismas rutas HTTP de importación/vínculo, misma forma de `runtime_binding_json`.

#### Dependencia legacy `TenantAgentVersion -> TenantVoiceAgentConfig`

- `TenantAgentVersion.voice_agent_config_id` es FK (`ondelete=SET NULL`) a `tenant_voice_agent_configs` (Voice Legacy, en `models/integrations.py`), con `relationship("TenantVoiceAgentConfig")`.
- Usos: `AgentService._validate_voice_agent_config` (pertenencia al tenant al crear/editar draft), copia al publicar, y `AgentCompilerService` sintetiza `realtime.voice` y el puente `settings.voice` desde `default_voice` cuando el draft no trae voz propia.
- Aislamiento sin romper compatibilidad:
  1. Mantener la columna y la FK (contrato de datos y API: `voice_agent_config_id` sigue en request/response).
  2. Quitar la `relationship` del ORM de Agent Builder y leer el config legacy a través de `voice_legacy.public.get_voice_agent_defaults(tenant_id, config_id) -> LegacyVoiceDefaults{default_voice}` (DTO), usado por la validación de draft y por el compilador.
  3. Backfill opcional: materializar `realtime.voice` en las versiones que aún dependen del puente, para que el compilador deje de necesitar el config legacy; retirar el puente sólo tras el smoke manual de agentes antiguos (ya previsto en `PROJECT_STATUS.md`).

### 3. Voice Orchestration

- **Ownership**: `voice_sessions`, `voice_session_events`, `tenant_voice_provider_configs` (traer desde Voice Legacy).
- **Entrantes**: Tools, Telephony (outbound, SIP QA), Agents, Voice Experiences (webhooks), endpoints `voice`/`voice_runtime`.
- **Salientes**: Agents, CRM (resolución de contexto, proyección), Telephony (SIP QA desde el endpoint), Voice Legacy (`voice_config_service`, `ultravox_ingestion_service`), Integrations (Chatwoot handoff), Billing/Analytics (`analytics.Call`).
- **API pública propuesta**: `VoiceSessionFacade` (existe: `get_tool_session`, `record_event`, `enrich_context` por id con `ContactRef`/`LeadRef`), `ToolSessionView` (existe), `create_session`, `dispatch`, `close_sessions_for_agent`, `SessionContextV1`, `RuntimeSessionSpecV1`, `resolve_runtime_credential`.
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
