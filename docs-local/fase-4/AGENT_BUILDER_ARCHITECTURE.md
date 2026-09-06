# Agent Builder — Arquitectura (Fase 1 + Fase 2)

## Objetivo

Invertir la dependencia actual de ServiGlobal respecto de Ultravox: en vez de
que el proveedor sea la fuente de verdad del agente, ServiGlobal pasa a serlo.
El proveedor (Ultravox hoy; LiveKit, OpenAI Realtime, etc. en el futuro) se
convierte en un ejecutor detrás de un `RuntimeBinding` compilado.

- **Fase 1**: `Agent`/`AgentVersion`, draft/publish, compatibilidad con
  `TenantVoiceAgentConfig`.
- **Fase 2**: Provider/Model/Capability Registry (catálogo estático) y
  selección explícita y validada de `pipeline_type`/`provider`/`model` desde
  la UI, en vez de un valor fijo "porque sí".

**Esta fase NO implementa LiveKit, tablas de registry en base de datos, ni un
`AgentRuntimeBinding` independiente.** Ver "Pendientes" al final.

## Dominio

```
Agent (TenantAgent)
 ├── identidad (name, description)
 ├── status: draft | active | archived
 ├── published_version_id  -> TenantAgentVersion | null
 └── draft_version_id      -> TenantAgentVersion | null

        │ 1:N
        ▼

AgentVersion (TenantAgentVersion)
 ├── version (int, único por agent_id)
 ├── status: draft | published | superseded
 ├── language, timezone
 ├── identity_json       {name, description}          (snapshot inmutable)
 ├── instructions_json   {role, objective, system_prompt, greeting, closing}
 ├── behavior_json       {response_style, interruptions, turn_detection,
 │                         confirmation_strategy, agent_first}
 ├── runtime_binding_json {pipeline_type: "realtime",
 │                          realtime: {provider, model}}
 └── voice_agent_config_id -> TenantVoiceAgentConfig | null   (compat legacy)
```

Modelos: `backend/app/models/agents.py`. Esquemas Pydantic:
`backend/app/schemas/agents.py`. Servicio: `backend/app/services/agent_service.py`.

**Por qué `TenantAgent` y no `Agent`**: ya existe `app.models.analytics.Agent`
(tabla `agents`), una entidad de analítica sincronizada 1:1 desde
`VoiceAgentService._sync_analytics_agent` y usada por la ingesta de llamadas
para resolver `Call.agent_id`. Es un concepto distinto y no relacionado. El
dominio nuevo sigue la convención del repositorio de prefijar con `Tenant`
toda entidad multi-tenant (`TenantVoiceAgentConfig`, `TenantVoiceExperience`,
`TenantFeatureGrant`, ...).

## Draft / Publish

El patrón replica el ya validado en `TenantVoiceExperience` /
`TenantVoiceExperienceVersion` (`backend/app/services/voice_experience_service.py`):

```
create_agent
    → Agent(status=draft) + AgentVersion v1 (status=draft)

update_draft (PATCH /agents/{id}/draft)
    → muta la versión draft actual in place

publish (POST /agents/{id}/publish)
    → requiere instructions.system_prompt no vacío
    → la versión draft pasa a status=published, published_at=now
    → la versión previamente publicada (si existía) pasa a status=superseded
    → Agent.published_version_id = nueva versión; draft_version_id = null;
      Agent.status = active

editar de nuevo (POST /agents/{id}/draft, sin body)
    → sólo si Agent.draft_version_id es null y existe published_version_id
    → copia identity/instructions/behavior/runtime_binding de la versión
      publicada en una nueva versión (version+1, status=draft)

archive (POST /agents/{id}/archive)
    → Agent.status = archived; el agente y sus versiones quedan inmutables
```

Una versión publicada nunca se muta. Editar un agente publicado siempre crea
una versión nueva (`Published V4 → Editar → Draft V5 → Publicar → Published V5`,
y V4 pasa a `superseded`).

## RuntimeBinding simplificado

En vez de una tabla `AgentRuntimeBinding` independiente (sigue diferida, ver
"Pendientes" — es una relación 1:1 con la versión, no aporta nada hoy),
cada `AgentVersion` embebe un `runtime_binding_json`:

```json
{ "pipeline_type": "realtime", "realtime": { "provider": "ultravox", "model": "ultravox" } }
```

Desde la Fase 2, este valor ya no lo infiere el backend en silencio: el
usuario lo elige explícitamente (`pipeline_type`/`provider`/`model` en
`AgentCreateRequest`/`AgentDraftUpdateRequest`, con default `realtime`/`ultravox`/`ultravox`)
y `AgentService._build_runtime_binding()` lo valida contra el
Provider/Model Registry (`validate_runtime_selection`, ver abajo) antes de
guardarlo — un `pipeline_type` distinto de `realtime`, un provider no
`active` o un modelo no `available` devuelven `422`.

## Provider / Model / Capability Registry (Fase 2)

Catálogo de plataforma en `backend/app/domain/voice_registry.py`: dataclasses
`frozen` (`VoiceProvider`, `VoiceModel`, `ParameterSpec`), **código estático
versionado en git, no tablas de base de datos** — mismo patrón ya usado en
este repo por el catálogo de notificaciones
(`app/domain/notification_event_schemas.py` + `NotificationAdminService.get_catalog()`).

Razón de la decisión: soportar un proveedor nuevo siempre requiere escribir
un adapter real (como `UltravoxLegacyRuntimeAdapter`); una tabla editable en
runtime no cambia esa realidad y sólo agregaría migraciones, seed y un CRUD
admin para datos que en la práctica sólo cambian con un deploy.

Contenido actual: `ultravox` es el único `VoiceProvider` con `status="active"`;
`openai`, `google`, `aws`, `deepgram`, `cartesia`, `elevenlabs`, `anthropic`
existen como `status="planned"` (visibles en la UI como "Próximamente", sin
ningún modelo asociado — no se fingen modelos "planned" por proveedor).
`ultravox:ultravox` es el único `VoiceModel` (`model_type="realtime"`,
`implementation_status="available"`), con sus `capabilities` (`tools`,
`voice_selection`, `turn_detection`, `interruptions`, `transcription`,
`function_calling`; `reasoning=false`).

Endpoints de sólo lectura, autenticados, sin filtro de tenant (es catálogo de
plataforma): `backend/app/api/endpoints/voice_registry.py`.

```
GET /api/v1/voice/providers
GET /api/v1/voice/models              (query: type, provider, status)
GET /api/v1/voice/models/{model_id}
GET /api/v1/voice/models/{model_id}/capabilities
```

## Compatibilidad con `TenantVoiceAgentConfig`

```
TenantAgent / TenantAgentVersion   (nuevo dominio, fuente de verdad)
            │
            │ voice_agent_config_id (FK opcional, SET NULL)
            ▼
TenantVoiceAgentConfig             (legacy, Ultravox)
            │
            ▼
UltravoxLegacyRuntimeAdapter.compile_settings()
            │
            ▼
VoiceClient / Ultravox             (sin cambios, no tocado por esta fase)
```

- `TenantVoiceAgentConfig` no se modifica ni se elimina. Los endpoints legacy
  (`GET/POST/PUT /api/v1/voice/agents`) siguen funcionando sin cambios.
- Un `AgentVersion` puede vincular un `voice_agent_config_id` existente. El
  vínculo es de sólo lectura desde el lado de Agent Builder: crear, editar o
  publicar un `TenantAgent` nunca escribe en `TenantVoiceAgentConfig`. Desde la
  Fase 2 este vínculo ya no decide el `provider` del `runtime_binding_json`
  (eso es explícito y viene del Registry) — sólo sirve para heredar
  prompt/voz por defecto vía `UltravoxLegacyRuntimeAdapter`.
- Migración de datos (`202609060001_agent_builder_foundation.py`): cada
  `TenantVoiceAgentConfig` existente genera automáticamente un `TenantAgent` +
  `AgentVersion v1` equivalente (activo y publicado si el config original
  tenía `status="active"`; en borrador en otro caso), vinculado vía
  `voice_agent_config_id`. `default_voice` y `default_tools_json` del config
  original no se duplican todavía en `AgentVersion` — siguen viviendo sólo en
  `TenantVoiceAgentConfig` hasta que exista un Model/Capability Registry que
  les dé un lugar tipado.
- `AgentRuntimeAdapter` (`backend/app/services/agent_runtime_adapter.py`) es
  la interfaz que aísla el dominio nuevo de Ultravox. `UltravoxLegacyRuntimeAdapter`
  implementa `compile_settings()` resolviendo prompt/voz/`provider_agent_id`
  desde `TenantVoiceAgentConfig` cuando hay vínculo. No ejecuta llamadas ni se
  invoca todavía desde ningún flujo real — es la frontera para próximas fases.

## Compilador

`backend/app/services/agent_compiler_service.py` expone
`compile_runtime_session_spec(agent, version) -> dict`, un primer
`AgentCompiler` que arma:

```json
{
  "agent_id": "...", "agent_version_id": "...", "tenant_id": "...",
  "instructions": {...}, "behavior": {...},
  "language": "es", "timezone": "America/Bogota",
  "pipeline": {"pipeline_type": "realtime", "realtime": {...}}
}
```

Sin secretos. No se persiste; se calcula bajo demanda.

## Seguridad y multi-tenancy

- Todos los endpoints (`backend/app/api/endpoints/agents.py`) resuelven
  `tenant_id` desde `AuthContext` (Auth0), nunca desde el body/query — mismo
  patrón que el resto de la plataforma (`backend/app/api/auth/deps.py`).
- Lectura: `platform_admin`, `tenant_admin`, `tenant_analyst`, `tenant_viewer`.
  Escritura/publish/archive: `platform_admin`, `tenant_admin`.
- Gateado por el feature flag `agent_builder_v2`
  (`TenantFeatureService`/`TenantFeatureGrant`), activable por tenant desde
  `/api/v1/admin/tenants/{id}/features` (sin UI nueva).
- `test_agent_builder.py` verifica que un tenant no puede leer, editar,
  publicar, archivar ni listar versiones de un agente de otro tenant (404 en
  todos los casos).
- Eventos sanitizados (`agent_created`, `agent_draft_updated`, `agent_published`,
  `agent_archived`) vía `IntegrationEventService`; nunca incluyen el
  `system_prompt` completo ni PII.

## Frontend

- Rutas: `frontend/app/[locale]/(tenant)/voice-ai/agents/` (`page.tsx` listado,
  `new/page.tsx`, `[agentId]/page.tsx`).
- Componente principal: `frontend/components/crm/agents/AgentBuilder.tsx`, con
  tabs General / Comportamiento / Voz y modelos / Versiones. "Voz y modelos"
  renderiza `PipelineTypeSelector` (sólo `realtime` habilitado; "Modular"/"Híbrida"
  con badge "Próximamente", sin lógica), y un `ProviderSelector`/`ModelSelector`
  reales alimentados por `GET /api/v1/voice/providers` y `/models` — las
  opciones no `active`/`available` aparecen como `<option disabled>` con
  "(Próximamente)", nunca seleccionables. Debajo se listan las `capabilities`
  del modelo elegido como badges de sólo lectura. El selector para vincular un
  `TenantVoiceAgentConfig` existente se mantiene aparte.
  Conocimiento/Herramientas/Flujos/Transferencias/Telefonía/Evaluaciones no
  existen todavía en esta fase (ni como placeholder).
- Cliente tipado `server-only`: `frontend/lib/api/agents.ts`. Mutaciones vía
  Server Actions (`voice-ai/agents/actions.ts`) — el bearer token nunca llega
  a un componente cliente, mismo patrón que Voice Experiences.
- Permisos: `frontend/lib/permissions/agents.ts` (mismos roles que el backend).

## Pendientes

Nada de lo siguiente existe todavía, ni como tabla, ni como endpoint, ni como
placeholder de UI con lógica detrás. Se documenta explícitamente para que no
se asuma implementado y para que quien retome el trabajo sepa dónde engancha
cada pieza con lo ya construido en Fase 1/Fase 2.

### 1. Dominio: RuntimeBinding y Registry

- **`AgentRuntimeBinding` como entidad independiente.** Hoy vive embebido en
  `AgentVersion.runtime_binding_json` (`backend/app/models/agents.py`). Es
  una relación 1:1 con la versión, así que una tabla aparte no se justifica
  todavía; se vuelve necesaria si un `AgentVersion` necesita más de un
  binding (p. ej. fallback entre proveedores) o si el binding necesita su
  propio ciclo de vida (auditoría, versionado independiente del contenido).
- **Provider/Model Registry en base de datos.** Hoy es catálogo estático en
  `backend/app/domain/voice_registry.py` (`VoiceProvider`, `VoiceModel`,
  `ParameterSpec`), decisión tomada explícitamente en Fase 2 para evitar
  migraciones/seed/CRUD admin sin valor real mientras cada proveedor nuevo
  siga requiriendo un adapter escrito a mano. Migrar a tabla se justifica el
  día que un `platform_admin` necesite activar/desactivar un modelo (p. ej.
  por incidente del proveedor) sin esperar un deploy.
- **`DynamicModelSettings` con parámetros editables.** `VoiceModel.parameters`
  ya existe en el esquema (`ParameterSpec`: `supported`/`min`/`max`/`default`)
  pero el único modelo real (`ultravox:ultravox`) no expone parámetros
  configurables, así que la UI sólo muestra `capabilities` de sólo lectura.
  Cobra sentido con el segundo provider real que tenga algo como
  `temperature` o `voice_id` configurable.
- **`voice_agent_config.default_voice` / `default_tools_json` no tienen lugar
  tipado en `AgentVersion`.** Siguen viviendo sólo en `TenantVoiceAgentConfig`
  legacy; Agent Builder los hereda indirectamente vía
  `UltravoxLegacyRuntimeAdapter.compile_settings()` pero no los expone ni
  los deja editar desde la nueva UI. Necesitan un campo propio (`voice`,
  `tools_json`?) el día que se quiera desacoplar por completo del config
  legacy.

### 2. Agent Builder — pestañas no construidas

Ninguna de estas existe hoy, ni siquiera como "Próximamente" visual (a
diferencia de "Modular"/"Híbrida" en Voz y modelos, que sí son intencionales):
**Conocimiento, Herramientas, Flujos, Transferencias, Telefonía,
Evaluaciones.** Cada una implica su propio modelo de datos y no debe
asumirse trivial:

- *Herramientas*: relacionar `TenantAgentVersion` con definiciones de tools
  (hoy sólo existe `TenantVoiceAgentConfig.default_tools_json`, sin tipar).
- *Conocimiento*: no hay ningún concepto de base de conocimiento/RAG en el
  backend actual.
- *Flujos*: distinto de WhatsApp Flow Studio (`whatsapp_flow_*`); no hay
  overlap de código reutilizable directo.
- *Transferencias*: hoy el único handoff existente es
  `TenantVoiceAgentConfig.handoff_*` hacia Chatwoot (ver
  `voice_handoff_service.py`); portarlo a `AgentVersion` es un rediseño, no
  una copia.
- *Telefonía*: pertenece al dominio SIP/Asterisk (`voice_sip_route_service.py`,
  `asterisk_provisioning_service.py`), no tocado por Agent Builder.
- *Evaluaciones*: no existe ningún concepto de evaluación/scoring de calidad
  de agente en el backend hoy.

### 3. Ejecución real / Runtime

```
RuntimeSessionSpec
     │
     ▼
ServiGlobal Voice Runtime   (nuevo)
     │
     ▼
LiveKit Agents
     │
     ▼
LiveKit Room
   ┌────┼─────┐
 WebRTC SIP  Human
```

- `AgentCompilerService.compile_runtime_session_spec()` existe pero no lo
  llama ningún flujo de ejecución real.
- `UltravoxLegacyRuntimeAdapter` existe pero no lo invoca `VoiceClient` ni
  ningún endpoint de llamadas — es sólo la frontera preparada.
- No existe `agent_version_id` en `CrmVoiceCall` ni en ningún registro de
  llamada real; no hay forma de saber, desde una llamada ya hecha, qué
  `AgentVersion` la originó.
- `VoiceSession`, Runtime Dispatcher, LiveKit Agents/SIP/WebRTC, OpenAI
  Realtime, Gemini Live, Nova Sonic, Grok Voice, pipelines STT→LLM→TTS
  independientes: nada de esto existe. Son los proveedores "planned" en el
  Registry esperando un adapter real.
- Human Handoff, Agent Copilot, routing/fallback automático entre modelos:
  sin diseño todavía.

### 4. Observabilidad

- Eventos implementados: `agent_created`, `agent_draft_updated`,
  `agent_published`, `agent_archived` (`IntegrationEventService`, provider
  sintético `"agent_builder"`).
- **No implementado**: un evento `runtime_binding_changed` separado cuando
  cambia específicamente `pipeline_type`/`provider`/`model` (hoy queda
  implícito dentro de `agent_draft_updated`, sin distinguirse en los logs).

### 5. Tests y QA

- No hay spec de Playwright para Agent Builder (creación, edición,
  publicación, versiones, selector de proveedor/modelo) — sí existe cobertura
  backend completa (`test_agent_builder.py`, `test_voice_registry.py`,
  `test_migration_agent_builder_backfill.py`).
- No se probó la UI en un navegador real en ninguna de las dos fases; sólo se
  verificó que el build genera las rutas y que lint/typecheck pasan.
- El aislamiento multi-tenant y la validación del Registry están cubiertos a
  nivel API; no hay test que ejercite `AgentCompilerService` directamente
  (es una función pura sin efectos secundarios, pero no tiene su propio
  archivo de test).

### 6. Migración de datos — limitación conocida

El backfill (`202609060001_agent_builder_foundation.py`) escribe
`runtime_binding_json` directamente con el `provider` del
`TenantVoiceAgentConfig` original, **sin pasar por
`validate_runtime_selection()`**. Si alguna vez existiera un
`TenantVoiceAgentConfig.provider` distinto de `"ultravox"` en datos reales,
el backfill igual lo escribiría (el Registry sólo se aplica a partir de esta
fase hacia adelante, vía `AgentService`). No se ha detectado ningún caso así
en el código ni en las migraciones existentes.

---

Esta fase deja `Agent`/`AgentVersion`/`AgentCompiler`/`AgentRuntimeAdapter`/`voice_registry`
como los puntos de extensión sobre los que construir lo anterior sin
remodelar el Agent Builder.
