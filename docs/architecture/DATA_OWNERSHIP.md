# Ownership de datos

Una sola base PostgreSQL, un solo `Base` SQLAlchemy y una sola cadena Alembic. El aislamiento es **lógico**: cada tabla tiene un módulo propietario, el único que la escribe y define sus invariantes. Otros módulos la leen o la modifican a través de la API pública del propietario. Las foreign keys entre módulos se mantienen: el objetivo no es separar bases de datos.

Estado: ✅ ya respetado · 🟡 propietario claro, pero otros módulos acceden directamente · 🔴 escrito por varios módulos.

## Identity / Tenancy

| Tabla | Modelo | Archivo actual | Estado |
| --- | --- | --- | --- |
| `tenants` | `Tenant` | `models/identity.py` | 🟡 leída en todas partes (FK universal; aceptable) |
| `users`, `tenant_memberships`, `access_audit_logs` | `User`, `TenantMembership`, `AccessAuditLog` | `models/identity.py` | 🟡 |
| `tenant_feature_grants` | `TenantFeatureGrant` | `models/tenant_features.py` | ✅ vía `TenantFeatureService` |

`app/db/mixins.py` (`TimestampMixin`, `_uuid`, `_utcnow`) es shared kernel; `models/identity.py` los reexporta por compatibilidad. `models/analytics.py` aún declara su propio `TimestampMixin` duplicado: unificar al migrar Analytics.

## Agent Builder (migrado)

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_agents` | `TenantAgent` (`app/modules/agents/infrastructure/models.py`) | ✅ Voice lo lee sólo vía `agents.public` (`PublishedAgent`, `AgentDisplay`, estado, nombres); la importación de agentes de proveedor la escribe Agent Builder |
| `tenant_agent_versions` | `TenantAgentVersion` (idem) | ✅ Agent Builder es el único que interpreta `runtime_binding_json` (Voice recibe `AgentToolBindingView`, el runtime recibe `RuntimeSessionSpecV1` compilado); Tool Platform pregunta vía `AgentsFacade`. FK legacy `voice_agent_config_id` → `tenant_voice_agent_configs` sin relación ORM: el valor se lee vía `voice_legacy.public` |
| `tenant_agent_scheduling_configs` | `TenantAgentSchedulingConfig` (`modules/scheduling/infrastructure/models.py`) | ✅ propietario Scheduling (configuración de agenda por agente) |

## Voice Orchestration

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `voice_sessions` | `VoiceSession` (`app/modules/voice/infrastructure/models.py`) | ✅ escrita sólo por Voice; Telephony pide cambios por `voice.public.VoiceTelephonyFacade` (vincular ruta/trunk, correlacionar `CrmVoiceCall`, dispatch, `sip_call_id`, cancelar) y consulta conteos con `count_active_telephony_sessions`; Agents ya no la escribe: al borrar un agente pide `voice.public.release_sessions_of_deleted_agent`. Sin relaciones ORM hacia las tablas de Agents (sólo FKs) |
| `voice_session_events` | `VoiceSessionEvent` (`app/modules/voice/infrastructure/models.py`) | ✅ Tool Platform escribe vía `VoiceSessionFacade.record_event(session_id, ...)`; la proyección lee `SessionProjectionFacts` |
| `tenant_voice_provider_configs` | `TenantVoiceProviderConfig` (`models/integrations.py`) | 🟡 propietario: **Voice Providers**; el runtime lo lee sólo vía `voice_providers.public.resolve_runtime_credential` (tenant derivado de la sesión). Lo escribe todavía `voice_config_service` (UI de Integraciones) |

## Telephony

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_sip_routes` | `TenantSipRoute` (`app/modules/telephony/infrastructure/models.py`) | ✅ propietario: **Telephony**. Misma tabla, FKs y constraints (sin migración). Fuera del módulo sólo se ve `SipRouteView`/`SipRouteConnection` (la contraseña SIP no aparece en vistas ni `repr`); `provider_config_id` referencia `tenant_voice_provider_configs`, de Voice Providers, que Telephony recibe como `ProviderConfigRef` |
| `crm_voice_calls`, `crm_voice_call_events` | `CrmVoiceCall`, `CrmVoiceCallEvent` | 🟡 propietario: **CRM**. Telephony ya no los toca: el outbound abre/actualiza el registro por `crm.public.OutboundCallLedger` y la carga legacy en vuelo se cuenta por `CallLoadPort`. Voice (proyección) y Voice Legacy aún los escriben |
| `tenant_integration_events` (`voice_capacity_*`, `voice_callback_*`, `voice.outbound.requested`, `voice.sip.dial.started`) | `TenantIntegrationEvent` | 🟡 auditoría compartida: Telephony escribe vía `IntegrationEventService.add_event` en la misma transacción |

## Tool Platform (migrado)

| Tabla | Modelo | Ubicación | Estado |
| --- | --- | --- | --- |
| `tenant_tools` | `TenantTool` | `app/modules/tools/infrastructure/models.py` | ✅ |
| `tenant_http_tool_configs` | `TenantHttpToolConfig` | idem | ✅ |
| `tenant_tool_credentials` | `TenantToolCredential` | idem | ✅ secretos sólo descifrables por `CustomHttpToolExecutor`; `tools.public` expone únicamente `is_custom_tool_credential_ready` |

Datos de otros módulos que Tool Platform usa, siempre vía API pública y como DTO inmutable, nunca como fila ORM: los bindings de la versión publicada y el `SessionContextV1` llegan dentro de `ToolSessionView` (Voice); la identidad CRM creada por `crm.create_lead` llega como `ContactRef`/`LeadRef`; la plantilla WhatsApp como `WhatsAppTemplateContract`; el "¿tool en uso?" como `bool` (`AgentsFacade`). Los eventos y el enriquecimiento de `VoiceSession` se piden a Voice por `session_id`. Los bindings de tools **se persisten dentro de** `TenantAgentVersion.runtime_binding_json`: el propietario de la fila es Agent Builder; Tool Platform es el propietario del **schema** de cada binding (`config`) y lo valida con `PlatformToolContractService`.

## CRM

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `crm_contacts`, `crm_leads` | `CrmContact`, `CrmLead` | ✅ propietario: **CRM** (ORM en `modules/crm/infrastructure/models.py`); el resto sólo ve `ContactProfile`/`LeadProfile`/snapshots por `crm.public` |
| `crm_pipeline_stages`, `crm_tasks`, `crm_call_contexts` | `CrmPipelineStage`, `CrmTask`, `CrmCallContext` | ✅ CRM. `assigned_to_user_id` se valida por `TaskAssigneePort` → `identity.public`; sin relaciones ORM a Identity |
| `crm_activities` | `CrmActivity` | ✅ CRM. Los demás módulos escriben por `crm.public` (`record_activity`, `stage_activity` en su transacción, `upsert_call_activity`); `call_id` es sólo un id hacia Analytics |
| `crm_voice_calls`, `crm_voice_call_events` | `CrmVoiceCall`, `CrmVoiceCallEvent` | ✅ CRM (propietario único). Telephony vía `OutboundCallLedger`/`CallLoadPort`; Voice Legacy (webhooks, callbacks, workers) y la proyección de Analytics vía `crm.public.CrmVoiceCalls`, que escribe en la transacción del llamador y nunca hace commit |
| `crm_whatsapp_messages` | `CrmWhatsAppMessage` | ✅ propietario: **Integrations / Messaging** (ORM en `modules/integrations/infrastructure/models.py`; el nombre histórico de la tabla no determina el dueño; mismas columnas, FKs e índices). CRM ya no lo importa: el borrado de leads lo desreferencia por `integrations.public.detach_lead_references`, y la acción WhatsApp/historial del lead se piden a `WhatsAppFacade`; Messaging escribe la actividad en `crm.public` |
| `crm_bookings`, `crm_booking_events` | `CrmBooking`, `CrmBookingEvent` | ✅ propietario: **Scheduling** (ORM en `modules/scheduling/infrastructure/models.py`; CRM sólo ve `BookingView`; FKs a `crm_leads`/`crm_contacts` a nivel DB, sin relaciones ORM) |

## Scheduling

Ahora en `app/modules/scheduling/infrastructure/models.py` (en la migración de código original: mismas tablas, FKs, índices y constraints, sin migración; el PR #121 añadió después `tenant_booking_operations` y `crm_bookings.scheduling_resource_id` con la migración `202609240001`).

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_booking_configs`, `tenant_voice_booking_configs` | `TenantBookingConfig`, `TenantVoiceBookingConfig` | ✅ Scheduling. La clave de Cal.com sólo existe cifrada (`cal_api_key_encrypted`) y nunca sale en vistas/DTOs; la config de voz solo se pide por id (`find_voice_booking_config_id`) |
| `tenant_google_calendar_connections`, `tenant_google_calendars` | `TenantGoogleCalendarConnection`, `TenantGoogleCalendar` | ✅ Scheduling. Tokens OAuth cifrados, sólo dentro de `infrastructure/google/` |
| `tenant_scheduling_configs`, `…_resources`, `…_resource_calendars`, `…_teams`, `…_team_members`, `…_exceptions`, `…_schedules`, `…_event_types`, `…_provider_objects` | `TenantScheduling*` | ✅ Scheduling (relaciones ORM internas permitidas) |
| `tenant_agent_scheduling_configs` | `TenantAgentSchedulingConfig` | ✅ Scheduling; Agent Builder sólo pregunta `is_booking_configured` |
| `crm_bookings`, `crm_booking_events` | `CrmBooking`, `CrmBookingEvent` | ✅ Scheduling. Historia propia del booking (≠ eventos de dominio). `scheduling_resource_id` (FK a `tenant_scheduling_resources`) es el recurso canónico y base de la guarda de solapes |
| `tenant_booking_operations` | `BookingOperation` | ✅ Scheduling. Operaciones idempotentes de booking (create/cancel/reschedule): unique `(tenant_id, operation_type, idempotency_key)`; `result_json` sólo ids/estado, nunca tokens ni PII |
| `tenant_integration_events` (`calcom_sync`, `booking_create`, `availability_lookup`, …) | `TenantIntegrationEvent` | ✅ propietario: **Integrations**; Scheduling escribe por `IntegrationEvents.record/add` (metadata sanitizada), nunca construye la fila |
| `domain_events` (`booking.*`) | `DomainEvent` | 🟡 los crea la infraestructura existente al anunciarse el hecho (`wiring.NotificationBookingEvents`); Scheduling no importa Notifications |

## Notifications

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients` | Modelos Notifications | Propiedad de Notifications |
| `domain_events` | `DomainEvent` | Notifications; Voice y Scheduling publican hechos por las entradas publicas |
| `notification_deliveries` | `NotificationDelivery` | Notifications; Messaging reporta estados por `notifications.public` |

## Integrations / Messaging

ORM en `app/modules/integrations/infrastructure/models.py` (13 tablas; mismas columnas, FKs, índices y constraints; sin migración). Sin relaciones ORM hacia `Tenant`, `User`, `CrmLead`, `CrmContact` ni `TenantVoiceContextSchema`: sólo FKs. Las relaciones entre sus propias tablas se conservan.

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_integrations` | `TenantIntegration` | ✅ catálogo on/off + salud genérica (`resend`, `voice`, `whatsapp`, `calcom`, `google_calendar`, `chatwoot`). No hace a Integrations dueño del proveedor: la config de Voice es de Voice y la de Cal.com/Google es de Scheduling |
| `tenant_integration_events` | `TenantIntegrationEvent` | ✅ auditoría transversal; se escribe sólo por `IntegrationEvents` (`api_key`, `authorization`, `payload`, `html`, `text`, `base64`, `phone`, `email` se redactan; los no escalares se omiten) |
| `tenant_whatsapp_configs`, `tenant_whatsapp_templates`, `tenant_whatsapp_flows` | `TenantWhatsApp*` | ✅ Messaging. Tokens cifrados (`access_token_encrypted`, `webhook_verify_token_encrypted`), nunca en DTOs/respuestas/logs. Flows lee el schema de contexto de Voice por `VoiceContextSchemaPort` (snapshot, sin ORM) |
| `crm_whatsapp_messages` | `CrmWhatsAppMessage` | ✅ ledger de mensajes (queued/sent/delivered/read/failed/received, `provider_message_id`, `notification_delivery_id`); el estado nunca retrocede. **Identidad protegida por PostgreSQL** (Sprint 8.1, migración `202610050001`): unique parcial `uq_crm_whatsapp_messages_tenant_provider_message` sobre `(tenant_id, provider_message_id) WHERE provider_message_id IS NOT NULL` (tenant-scoped: asume un proveedor WhatsApp por tenant; con varios habría que incluir `provider`) |
| `tenant_email_configs`, `tenant_email_templates`, `tenant_email_assets`, `tenant_email_sends`, `tenant_email_send_assets` | `TenantEmail*` | ✅ Messaging. Los archivos viven en Storage (`AssetStoragePort`); el enlace a formularios se valida por `FormLinkPort` |
| `tenant_chatwoot_configs`, `tenant_chatwoot_inboxes` | `TenantChatwoot*` | ✅ Messaging. `api_token_encrypted`; `webhook_key` opaco; unique `(base_url, account_id)` |

**Residuo temporal** en `app/models/integrations.py` (no son de Messaging, sin alias ni reexport): Forms (`tenant_forms`, `tenant_form_fields`, `tenant_form_tokens`, `tenant_form_submissions`, `tenant_form_submission_answers`) y config legacy de Voice (`tenant_voice_provider_configs`, `tenant_voice_agent_configs`). `test_integrations_boundaries.py` impide que una clase de Messaging vuelva allí y `app/models/crm.py` ya no existe.

## Voice Experiences

Owner: app.modules.voice_experiences.infrastructure.models para tenant_voice_experiences, tenant_voice_experience_versions, tenant_voice_context_schemas, tenant_voice_context_fields, tenant_voice_experience_submissions, tenant_voice_experience_submission_values, tenant_voice_context_sessions, tenant_voice_runtime_calls y voice_public_rate_limit_windows. Las tablas CRM, Billing, Telephony, Identity y Voice Legacy siguen con sus owners; Forms no pertenece a Voice Experiences.
Responsabilidades: contenido/tema, consentimiento, captura de contexto, schemas versionados, submissions públicas, token one-shot, política y lifecycle de launch. No es owner de Agent prompt/runtime config, VoiceSession, LiveKit, SIP, Telephony, CRM, Billing, credenciales, tools ni evaluaciones.
Deuda temporal: agent_config_id sigue hasta PR #134; runtime público directo de proveedor hasta PR #135; callback directo de proveedor/SIP hasta PR #136. TenantVoiceRuntimeCall es por ahora el ledger del launch legacy.

## Voice Legacy y Analytics

- Voice Legacy: `tenant_voice_agent_configs` (`TenantVoiceAgentConfig`). Sincroniza su agente de reporting por `analytics.public.AnalyticsAgentDirectory`.
- Analytics: ver la sección «Analytics (Module 11)».

## Billing (Module 10)

| Tabla | Modelo | Archivo actual | Estado |
| --- | --- | --- | --- |
| `tenant_billing_plans` | `TenantBillingPlan` | `modules/billing/infrastructure/models.py` | ✅ Billing |
| `tenant_usage_alerts` | `TenantUsageAlert` | `modules/billing/infrastructure/models.py` | ✅ Billing |
| `external_provider_pricing` | `ExternalProviderPricing` | `modules/billing/infrastructure/models.py` | ✅ Billing |

Billing consume minutos facturados mediante `UsageMeterPort`; respaldado por `analytics.public.AnalyticsUsageFacts` (conserva el límite inclusivo `started_at <= billing_period_end`). Analytics es dueño de los hechos de llamada.

## Reglas

1. Un módulo nuevo declara sus tablas en `app/modules/<m>/infrastructure/models.py` y las registra en `app/models/__init__.py` (Alembic).
2. Nunca escribir la tabla de otro módulo; pedirlo a su `public.py` o reaccionar a un evento.
3. Leer datos de otro módulo: preferir un query service en su `public.py`. Las lecturas directas existentes (🟡) se eliminan al migrar el módulo lector.
4. No crear schemas PostgreSQL por módulo ni bases separadas.


## Identity / Tenancy (Module 9)

| Table | Owner |
| --- | --- |
| `tenants` | Identity |
| `users` | Identity |
| `tenant_memberships` | Identity |
| `access_audit_logs` | Identity |
| `tenant_feature_grants` | Identity |

Billing owns `tenant_billing_plans`, `tenant_usage_alerts`, and `external_provider_pricing`. Analytics owns `agents`, `calls`, `call_events`, and `metric_snapshots_daily`. Agent Builder `TenantAgent` data is outside Identity.

Only Identity imports `User`, `TenantMembership`, `AccessAuditLog` and `TenantFeatureGrant`. `Tenant` remains read directly by legacy Analytics/Voice Legacy/Voice Experiences files listed in `test_identity_architecture.TENANT_DIRECT_READERS`; they are removed when those owner modules migrate.

Billing's `tenant_id -> tenants.id` foreign keys do not create cross-module ORM navigation; its plan-alert relationship remains internal to Billing.

## Analytics (Module 11)

```text
Analytics
├── agents                  Agent                 (reporting/provider projection)
├── calls                   Call
├── call_events             CallEvent
└── metric_snapshots_daily  MetricSnapshotDaily
```

| Dueño | Tablas |
| --- | --- |
| Analytics | `agents`, `calls`, `call_events`, `metric_snapshots_daily` (`modules/analytics/infrastructure/models.py`) |
| Agent Builder | `tenant_agents`, `tenant_agent_versions` (identidad canónica; no se fusiona con `agents`) |
| CRM | `crm_voice_calls`, `crm_voice_call_events`, `crm_activities`, … |
| Voice | `voice_sessions`, `voice_session_events` |

`agents` es una dimensión analítica (`Call.agent_id`, distribuciones de dashboard, correlación con el proveedor); la clase ORM conserva el nombre `Agent` y la ambigüedad se resuelve por módulo y DTO (`AnalyticsAgentView`). Nadie fuera de Analytics importa su ORM (`test_analytics_boundaries`); la única excepción de herramienta es `scripts/seed_staging_analytics.py` (seed de staging). `call_events.dedup_key` sigue siendo único global (`uq_call_events_dedup_key`). Escrituras externas: Voice/Telephony proyectan sesiones vía `VoiceCallProjectionFacade`; Ultravox y el webhook del runtime escriben por `AnalyticsCallLedger`; Identity limpia por `AnalyticsMaintenance` (sólo flush).

## Voice Experiences — binding canónico
Voice Experiences sigue siendo owner de `tenant_voice_experiences` y `tenant_voice_experience_versions`. `agent_id` identifica el Agent canónico de cada experiencia; `agent_id` + `agent_version_id` en ExperienceVersion fijan el AgentVersion usado por esa publicación. Agent Builder conserva el ownership de `tenant_agents` y `tenant_agent_versions`; la consulta y el bloqueo de publicación cruzan únicamente `agents.public`. Los campos `agent_config_id` permanecen por compatibilidad hasta completar PR #134/#135/#136.
