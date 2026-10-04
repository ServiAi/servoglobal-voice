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
| `crm_contacts`, `crm_leads` | `CrmContact`, `CrmLead` | 🔴 escritos por CRM, Voice (resolución/proyección), Voice Legacy (ingestión), Tool Platform (vía `CrmFacade`, recibe sólo `ContactRef`/`LeadRef` ✅) |
| `crm_pipeline_stages`, `crm_tasks`, `crm_call_contexts` | … | 🟡 |
| `crm_activities` | `CrmActivity` | 🔴 escrita por Scheduling, Integrations, Voice, Voice Legacy → objetivo: evento o `crm.public.record_activity` |
| `crm_voice_calls`, `crm_voice_call_events` | `CrmVoiceCall`, `CrmVoiceCallEvent` | 🟡 CRM (propietario); Telephony ya sólo vía `OutboundCallLedger`/`CallLoadPort`; Voice (projection) y Voice Legacy aún escriben |
| `crm_whatsapp_messages` | `CrmWhatsAppMessage` | 🔴 propietario objetivo: Messaging (el mensaje es del canal; CRM lo muestra en timeline) |
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
| `tenant_integration_events` (`calcom_sync`, `booking_create`, `availability_lookup`, …) | `TenantIntegrationEvent` | 🟡 auditoría compartida de integraciones (temporal, allowlist `SCHEDULING_LEGACY_ALLOWED`) |
| `domain_events` (`booking.*`) | `DomainEvent` | 🟡 los crea la infraestructura existente al anunciarse el hecho (`wiring.NotificationBookingEvents`); Scheduling no importa Notifications |

## Notifications

| Tabla | Modelo | Estado |
| --- | --- | --- |
| `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients` | … | ✅ |
| `domain_events` | `DomainEvent` | 🟡 escrita por Voice y, para `booking.*`, por la infraestructura de eventos vía el puerto de Scheduling (patrón correcto; exponer como `notifications.public`) |
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
