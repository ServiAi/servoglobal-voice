# Ownership de datos

Una sola base PostgreSQL, un solo `Base` SQLAlchemy y una sola cadena Alembic. El aislamiento es **lógico**: cada tabla tiene un módulo propietario, el único que la escribe y define sus invariantes. Otros módulos la leen o la modifican a través de la API pública del propietario. Las foreign keys entre módulos se mantienen: el objetivo no es separar bases de datos.

Estado: ✅ ya respetado · 🟡 propietario claro, pero otros módulos acceden directamente · 🔴 escrito por varios módulos.

## Identity / Tenancy

| Tabla | Modelo | Archivo actual | Estado |
| --- | --- | --- | --- |
| `tenants` | `Tenant` | `models/identity.py` | 🟡 leída en todas partes (FK universal; aceptable) |
| `users`, `tenant_memberships`, `access_audit_logs` | `User`, `TenantMembership`, `AccessAuditLog` | `models/identity.py` | 🟡 |
| `tenant_feature_grants` | `TenantFeatureGrant` | `models/tenant_features.py` | ✅ vía `TenantFeatureService` |

`app/db/mixins.py` (`TimestampMixin`, `_uuid`, `_utcnow`) es shared kernel; `models/identity.py` los reexporta por compatibilidad. `models/analytics.py` y `models/billing.py` aún declaran su propio `TimestampMixin` duplicado: unificar al migrar esos módulos.

## Agent Builder

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_agents` | `TenantAgent` | 🟡 Voice (`voice_session_service`, projection) lo lee directamente |
| `tenant_agent_versions` | `TenantAgentVersion` | 🟡 Voice lo lee (y lo proyecta a `ToolSessionView.tool_bindings`); Tool Platform pregunta vía `AgentsFacade` ✅. FK legacy `voice_agent_config_id` → `tenant_voice_agent_configs` (ver plan de aislamiento en `MODULAR_MONOLITH_MIGRATION.md`) |
| `tenant_agent_scheduling_configs` | `TenantAgentSchedulingConfig` (`models/integrations.py`) | 🟡 propietario Scheduling (configuración de agenda por agente) |

## Voice Orchestration

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `voice_sessions` | `VoiceSession` | 🔴 escrita por Voice, Telephony (outbound/SIP QA) y Agents (cancelación al borrar agente) |
| `voice_session_events` | `VoiceSessionEvent` | 🟡 Tool Platform escribe vía `VoiceSessionFacade.record_event(session_id, ...)` ✅ |
| `tenant_voice_provider_configs` | `TenantVoiceProviderConfig` (`models/integrations.py`) | 🟡 hoy lo gestiona `voice_config_service` (Voice Legacy); propietario objetivo: Voice Orchestration |

## Telephony

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_sip_routes` | `TenantSipRoute` (`models/integrations.py`) | 🟡 |

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
| `crm_contacts`, `crm_leads` | `CrmContact`, `CrmLead` | 🔴 escritos por CRM, Voice (resolución/proyección), Voice Legacy (ingestión), Tool Platform (vía `CrmFacade`, recibe sólo `ContactRef`/`LeadRef` ✅) |
| `crm_pipeline_stages`, `crm_tasks`, `crm_call_contexts` | … | 🟡 |
| `crm_activities` | `CrmActivity` | 🔴 escrita por Scheduling, Integrations, Voice, Voice Legacy → objetivo: evento o `crm.public.record_activity` |
| `crm_voice_calls`, `crm_voice_call_events` | `CrmVoiceCall`, `CrmVoiceCallEvent` | 🔴 Telephony (outbound), Voice (projection), Voice Legacy |
| `crm_whatsapp_messages` | `CrmWhatsAppMessage` | 🔴 propietario objetivo: Messaging (el mensaje es del canal; CRM lo muestra en timeline) |
| `crm_bookings`, `crm_booking_events` | `CrmBooking`, `CrmBookingEvent` | 🔴 propietario objetivo: **Scheduling** (`BookingService` gobierna su ciclo de vida) |

## Scheduling

Tablas en `models/integrations.py`: `tenant_booking_configs`, `tenant_google_calendar_connections`, `tenant_google_calendars`, `tenant_scheduling_resources`, `tenant_scheduling_resource_calendars`, `tenant_scheduling_configs`, `tenant_scheduling_teams`, `tenant_scheduling_team_members`, `tenant_scheduling_exceptions`, `tenant_scheduling_schedules`, `tenant_scheduling_event_types`, `tenant_scheduling_provider_objects`, `tenant_agent_scheduling_configs`, `tenant_voice_booking_configs`. Estado 🟡; al migrar, extraer a `app/modules/scheduling/infrastructure/models.py`.

## Notifications

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients` | … | ✅ |
| `domain_events` | `DomainEvent` | 🟡 escrita por Scheduling y Voice vía `NotificationEventPipeline` (patrón correcto; exponer como `notifications.public`) |
| `notification_deliveries` | `NotificationDelivery` | 🔴 `whatsapp_message_service` actualiza su estado directamente |

## Integrations / Messaging

`tenant_integrations`, `tenant_integration_events` (auditoría transversal → shared), `tenant_whatsapp_configs`, `tenant_whatsapp_templates`, `tenant_whatsapp_flows`, `tenant_email_configs`, `tenant_email_templates`, `tenant_email_assets`, `tenant_email_sends`, `tenant_email_send_assets`, `tenant_chatwoot_configs`, `tenant_chatwoot_inboxes`. Estado 🟡. `TenantWhatsAppTemplate` ya se consulta desde tools vía `WhatsAppFacade` ✅.

## Voice Experiences

`tenant_voice_experiences`, `tenant_voice_experience_versions`, `tenant_voice_context_schemas`, `tenant_voice_context_fields`, `tenant_voice_experience_submissions` y derivadas, `tenant_voice_context_sessions`, `tenant_voice_runtime_calls`, `voice_public_rate_limit_windows`, `tenant_forms`, `tenant_form_fields`, `tenant_form_tokens`, `tenant_form_submissions`, `tenant_form_submission_answers`. Estado 🟡 (`voice_context` es leído por WhatsApp Flows para generar formularios).

## Voice Legacy y Billing/Analytics

- Voice Legacy: `tenant_voice_agent_configs` (`TenantVoiceAgentConfig`), `agents` (`analytics.Agent`, legacy).
- Billing/Analytics: `tenant_billing_plans`, `tenant_usage_alerts`, `external_provider_pricing`, `calls`, `call_events`, `metric_snapshots_daily`. `calls` 🔴: escrita por Voice (projection) y Voice Legacy (ingestión); propietario objetivo Analytics, alimentado por eventos de sesión.

## Reglas

1. Un módulo nuevo declara sus tablas en `app/modules/<m>/infrastructure/models.py` y las registra en `app/models/__init__.py` (Alembic).
2. Nunca escribir la tabla de otro módulo; pedirlo a su `public.py` o reaccionar a un evento.
3. Leer datos de otro módulo: preferir un query service en su `public.py`. Las lecturas directas existentes (🟡) se eliminan al migrar el módulo lector.
4. No crear schemas PostgreSQL por módulo ni bases separadas.
