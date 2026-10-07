# Module 12 — Evaluations Discovery Report

**Fecha:** 2026-10-07
**Base local observada:** `develop` en `37c5758` (`Merge pull request #128 from ServiAi/refactor/modular-analytics`)
**Estado de actualización remota:** confirmado después del discovery. El preflight de PR #129 logró `git fetch origin` y `git pull --ff-only origin develop`; devolvió `Already up to date` sobre `37c5758`. La implementación vive en `refactor/modular-evaluations`.
**Alcance:** discovery y diseño. No se modificaron modelos, rutas, servicios, contratos, migraciones ni código de runtime. Este documento es el único artefacto preparado para entregar el resultado.

## 1. Executive Summary

**CONFIRMED.** En la base local no aparece un bounded context `app.modules.evaluations` ni modelos/tablas de evaluación. Sí existen piezas que servirían como evidencia: `VoiceSession`/`VoiceSessionEvent` en Voice, `Call`/`CallEvent` y summaries en Analytics, las versiones publicadas de Agent Builder, eventos de uso de tools y persistencia de bookings en Scheduling. El QA Harness usa sesiones `purpose="qa"`, pero no produce un `EvaluationRun`, rubric, score ni resultado de QA persistido como entidad propia.

**INFERRED.** La mayor parte de una evaluación técnica determinística puede derivarse de estados y eventos ya persistidos. La transcripción completa y los argumentos/resultados de tools no se exponen de forma uniforme por una frontera pública de evidencia y los eventos de tool se describen intencionalmente sin esos datos. Evaluación semántica, cumplimiento y calidad requieren una política explícita de evidencia y, probablemente, procesamiento LLM.

**RECOMMENDED.** Introducir Evaluations como owner de definiciones/versiones de rúbrica y resultados inmutables, consumiendo snapshots versionados de evidencia mediante DTOs públicos/eventos. No mover `Call`, `CallEvent`, Voice sessions, bookings, CRM activities ni Agent versions. El cierre de llamada debe quedar desacoplado de evaluaciones LLM mediante evento/outbox durable y worker con claim/lease/idempotencia. PR #129 debe comenzar por un vertical mínimo con evaluación determinística; LLM-as-a-Judge y reglas extensas de negocio pueden ser follow-ups.

**Limitación importante:** el `git pull` requerido no fue posible por ACL de `.git/FETCH_HEAD`; los hallazgos describen la base local observada, no garantizan el último estado de `origin/develop`.

## 2. Current Repository State

- **CONFIRMED en el discovery:** `git rev-parse --show-toplevel` → `G:/SERVIGLOBALAI/agente_inmobiliario/landing-serviglobalAi`; rama `develop`; HEAD `37c5758`; sin cambios locales antes de crear este reporte. En el preflight posterior de PR #129, `origin/develop` se confirmó actualizado y se creó `refactor/modular-evaluations`.
- **CONFIRMED:** `git remote get-url origin` → `https://github.com/ServiAi/servoglobal-voice.git`; HEAD local `37c5758`, merge de PR #128 / Analytics.
- **Resuelto después del discovery:** el primer `git pull` falló por permiso de `.git/FETCH_HEAD`; tras la autorización del usuario, `fetch` y `pull --ff-only` se completaron y confirmaron `Already up to date`. El reporte de discovery conserva el estado histórico del momento en que se redactó.
- **CONFIRMED:** CodeGraph reportó 889 archivos indexados, 15,702 nodos y 17,250 edges. Su exploración se usó como herramienta principal; el índice no devolvió búsqueda por lenguaje natural de varios términos, por lo que se consultaron nombres específicos y archivos adicionales señalados por CodeGraph.
- **Scope negativo:** no se ejecutaron pruebas, migraciones ni cambios de aplicación. La tarea pide auditoría; no pidió validación de una implementación.

## 3. Existing Evaluation-Like Capabilities

| Capacidad | Evidencia actual | Estado |
|---|---|---|
| Call outcome técnico | `Call.normalized_status`, tiempos y duración | Hecho de Analytics, no score de calidad |
| Call/session lifecycle | `VoiceSession.status` y `VoiceSessionEvent` | Hechos de Voice, no evaluación |
| Tool success/failure | Evento `session.context.tool_used` con `tool_key`, `status`, duración y código de error sanitizado | Telemetría parcial |
| Business booking result | Scheduling `BookingService` y evento de booking | Hecho de Scheduling; no evaluación del diálogo |
| Call summary | `CallSummaryService` compone CRM activity/context/lead y resumen de Analytics | Composición para CRM/email, no resultado de QA |
| Agent QA call | Harness con sesiones QA WebRTC/SIP y polling de eventos | Ejecución de prueba, sin score/rubric persistida |
| Sentiment, rubric, judge, assertion, compliance | No se halló entidad formal en las búsquedas de símbolos examinadas | No confirmado como capacidad existente |

La última fila no prueba ausencia de cualquier uso disperso en el repo: el vocabulario es amplio y CodeGraph no resuelve búsquedas por listas de sinónimos en una sola consulta. Antes de implementar se recomienda una segunda barrida lexical acotada con `rg` sobre backend, migraciones y frontend para confirmar negativos específicos.

## 4. Existing Models and Tables

| Modelo / tabla | Archivo / owner aparente | Relaciones y evidencia relevante | Productores / consumidores conocidos |
|---|---|---|---|
| `Call` / `calls` | `backend/app/modules/analytics/infrastructure/models.py` — Analytics | FK a `tenants` y `agents`; estado normalizado, inicio/fin, duración, minutos facturables, summary, canal/dirección, `recording_url`, teléfono | Analytics ingestión/proyección y consultas; `CallLookup` sirve resumen a `CallSummaryService`; Billing consume usage facts por frontera pública |
| `CallEvent` / `call_events` | mismo archivo — Analytics | FK a call/tenant, `event_type`, `payload_json`, provider ID, dedup key única | Analytics registra/consulta; vista pública `CallEventView` no incluye payload, solo metadatos |
| `MetricSnapshotDaily` | mismo archivo — Analytics | snapshot de reporting por día/agent | Analytics dashboard/maintenance |
| `Agent` / `agents` | mismo archivo — proyección de Analytics, distinta de Agent Builder | FK tenant; identidad externa provider/agent; relaciones a calls y snapshots | Analytics; no es identidad canónica ni configuración del agente |
| `VoiceSession` / `voice_sessions` | `backend/app/modules/voice/infrastructure/models.py` — Voice | FK tenant, Agent version, CRM voice call y SIP route; status/channel/direction/purpose; provider/session IDs; timestamps; JSON de `SessionContextV1`; idempotencia por `(tenant_id,idempotency_key)` | Control plane, runtime/control, QA Harness y adapter de Analytics projection |
| `VoiceSessionEvent` / `voice_session_events` | mismo archivo — Voice | FK tenant/session; event ID único, event type/source/sequence, JSON payload y timestamps | Runtime/control plane/tool dispatch; leído por QA Harness y proyección Analytics |
| `TenantAgent` / `tenant_agents` | `backend/app/modules/agents/infrastructure/models.py` — Agents | FK tenant, identity/status, referencias a versión publicada y draft | Agent Builder; consumido por compile/publish y Voice vía `agents.public` |
| `TenantAgentVersion` / `tenant_agent_versions` | mismo archivo — Agents | FK agent/tenant; unique `(agent_id,version)`; `identity_json`, `instructions_json`, `behavior_json`, `runtime_binding_json`, language/timezone/status | Agent Builder publica versiones; Voice fija `agent_version_id` en la sesión |
| Booking y entidades de CRM | Scheduling / CRM | No se completó inventario de cada tabla/relación en este discovery | Booking service y CRM poseen sus respectivos hechos; deben consultarse por sus boundaries, no por FK/import directo desde Evaluations |

En los modelos inspeccionados no aparece tabla formal `evaluations`, `evaluation_runs`, `criterion_results`, rubric o score. No se propone migrar tablas Analytics/Voice/CRM a Evaluations.

## 5. Existing Services

| Servicio | Responsabilidad / IO | Dependencias y consumidores | Mezcla de responsabilidades |
|---|---|---|---|
| `AnalyticsCallService` / `AnalyticsQueryService` (Analytics) | Escribe/consulta call facts y call events; create-or-update y dedup por `dedup_key`; consultas por tenant | `AnalyticsCallLedger`, `CallLookup`, proyección y otros adapters | No debe convertirse en evaluator; conserva hechos “qué ocurrió” |
| `VoiceSessionService` (Voice) | Crea sesión tenant-scoped, resuelve snapshot confiable, transiciona lifecycle, registra eventos y fallos | APIs/runtime, tools, QA | Responsabilidad correcta de Voice; contiene la sesión, no calidad post-call |
| `ToolDispatchService` (Tools) | Revalida sesión/binding/tenant, ejecuta Platform Tool o Custom Tool, registra estado y duración | Tool routes/runtime callbacks; `CustomHttpToolExecutor` | Correctamente ejecuta tools. No debe decidir score de conversación |
| `BookingService` (Scheduling) | Orquesta reservas/configuración e informa eventos de booking de forma segura | Platform tool calendar y otros consumers por ports | Owner del resultado de booking, no de score del agente |
| `CallSummaryService` (`backend/app/services/call_summary_service.py`) | Lee lead vía `CrmFacade`, luego busca summary en CRM activity, Analytics `CallLookup`, contexto CRM o lead; compone variables y crea asset de Email con actividad CRM | CRM, Analytics y Email facades; usado por Integrations/email composition | **Sí mezcla composición CRM + Analytics + Email.** No es Evaluation ni una fuente de resultado autoritativa |

No se completó un inventario estático de todos los consumidores/productores de cada servicio; los indicados son los confirmados en el contexto del índice y las fachadas observadas.

## 6. QA Harness Findings

- **CONFIRMED:** `AgentVoiceTest.tsx` permite transport WebRTC/SIP y contexto preloaded/conversation, solicita sesión de prueba, consulta contexto previo, crea token WebRTC cuando aplica y sondea eventos aproximadamente cada segundo hasta estado terminal. Deduplica eventos en UI por `event_id`.
- **CONFIRMED:** backend marca la sesión `purpose="qa"`; el modo conversation rechaza contexto preinyectado para evitar que una prueba conversacional herede identidad CRM no confiable. El servicio crea snapshot con `ContactResolutionService`.
- **CONFIRMED:** sesiones y eventos se persisten en `voice_sessions`/`voice_session_events`; event IDs son únicos. Las sesiones retienen `agent_version_id`, provider/channel y terminal status/timestamps.
- **CONFIRMED:** ToolDispatch registra evento de sesión con `tool_key`, éxito/error, duración y código seguro; evita incluir argumentos completos/resultados por disciplina de PII. El Custom Tool sigue el dispatcher común, pero el resumen persistido de éxito es genérico (`completed`).
- **CONFIRMED:** este Harness no crea ni persiste score, rúbrica, criterion result, éxito de objetivo o resultado de evaluación. La UI representa lifecycle/eventos; no es repositorio de evaluación.
- **GAP / no demostrado:** evidencia uniforme para transcripción completa, latencia por turno, interrupciones, invocation ID vinculado durablemente al resultado, argumentos/resultados normalizados y outcome final. Algunos eventos runtime pueden tener contenido transcrito, pero no se validó su retención completa ni su disponibilidad pública para evaluación.
- **RECOMMENDED:** un runner de Evaluations debe aceptar explícitamente `purpose=qa` y production sin cambiar el comportamiento del harness; la primera integración solo dispara evaluación posterior a sesión terminal y almacena un resultado independiente.

## 7. Voice Runtime Findings

El camino observable del control plane es: creación de `VoiceSession` (`requested`) → dispatch/starting/connected mediante transición y eventos → `ending`/`ended`, `failed` o `cancelled`, con timestamps y códigos sanitizados. El proveedor/runtime emite eventos y Voice los acepta mediante contratos runtime; `VoiceSessionEvent` sirve de ledger de lifecycle. `Analytics` tiene `VoiceCallProjectionFacade` con DTO de sesión/eventos para proyectar hechos al modelo de llamadas.

**CONFIRMED:** `VoiceSession.provider` y `provider_session_id` existen como identificadores; modelo además tiene columnas específicas de LiveKit. `VoiceSessionService` guarda errores en códigos y mensaje sanitizado y el evento de fallo carga código, no payload completo de excepción.

**Boundary recomendado:** evaluación se inicia desde la aplicación/orquestación de cierre al publicarse un evento de dominio terminal. Evaluations consume un DTO canónico y no importa ni nombra Ultravox, LiveKit, ElevenLabs u OpenAI en domain/application. Un adapter convierte Voice/Analytics event en evidencia neutral. El proveedor de voz no debe esperar a un judge LLM.

**Falta confirmar:** si cada terminal transition ya publica un evento durable/outbox común que permita arrancar evaluación tras commit. La evidencia observada confirma ledger de eventos y un pipeline/outbox de otros dominios, pero no demuestra un outbox universal de voz.

## 8. Analytics Boundary Findings

`app.modules.analytics.public` es import-light: evita SQLAlchemy en import público, acepta sesión tipada como `object`, carga servicios internamente y retorna DTOs en lugar de ORM. Facades observadas: `AnalyticsCallLedger`, `CallLookup`, `AnalyticsCallMetrics`, `AnalyticsUsageFacts`, `AnalyticsAgentDirectory`, `AnalyticsDashboard`, `AnalyticsMaintenance`, `VoiceCallProjectionFacade` y `AnalyticsFacade`.

Datos reutilizables: CallView (status/duración/summary y datos de coste medido en minutos), CallSummaryFact, métricas, uso facturado y proyección de sesiones/eventos. Los consumidores deben importar únicamente `app.modules.analytics.public` y sus contratos documentados; prohibido importar `analytics.infrastructure` o modelos internos.

**Missing public capability (por validar en detalle):** una consulta neutral de evidencia para evaluación que retorne call/session hechos requeridos, eventos filtrados y su versión/cursor de snapshot. `CallEventView` no devuelve `payload_json`; `CallView` devuelve `recording_url` y `customer_phone`, que Evaluations no debería recibir salvo necesidad justificada. La proyección de Voice expone datos sensibles como DTO para uso de Analytics, pero debe minimizarse antes de reutilizar.

Analytics describe “qué ocurrió” y mantiene Call/CallEvent/metrics. No debe almacenar resultados de calidad, rubrics ni criterio de éxito de negocio inferido.

## 9. Agent Builder Findings

`TenantAgentVersion` es fuente versionada con identity, instructions, behavior, bindings de tools/voz y provider/model bajo configuración runtime. Voice fija el ID de la versión publicada usada en cada sesión; esa referencia inmutable es clave para reproducir el contexto que originó una conversación.

Campos que pueden alimentar expectativas futuras: `identity_json` para rol/nombre; `instructions_json` para objetivo e instrucciones; `behavior_json` para estilo/flujo; tool bindings para herramientas habilitadas/config fija; runtime binding para idioma/model/provider/voz. No todos equivalen automáticamente a criterios verificables; una rubric debe seleccionar y congelar referencias/campos permitidos por versión.

Evaluations no debe leer modelos internos de Agents. **Missing public capability:** obtener snapshot mínimo e inmutable de la versión (o referencias al snapshot permitido) para evaluar adherencia sin reconsultar una configuración que pudo cambiar. `AgentsFacade` público debe ser la única entrada si esa capability no existe ya.

## 10. Platform Tools / Custom Tools Findings

Platform Tool y Custom Tool comparten `ToolDispatchService`; `custom.*` resuelve catálogo tenant-scoped y pasa a `CustomHttpToolExecutor`; Platform Tools verifican contrato/args/context y ejecutan handlers. La sesión aporta `SessionContextV1`, y el dispatcher deriva tenant desde la sesión.

| Dato | Estado observado |
|---|---|
| tool key/name, éxito/error, duración, error code | Persistido como evento sanitizado de Voice session |
| invocation ID | Aceptado por dispatcher; Platform Tool forma idempotency key `voice:{session}:{invocation_id}` cuando existe; persistencia y exposición común no confirmadas |
| argumentos LLM vs contexto confiable/config fija | Dispatcher los distingue al formar invocation; no se guardan en evento de sesión |
| resultado completo | Retornado a runtime/consumidor; no se observó persistencia de resultado completo en telemetría de sesión |
| Platform vs Custom | Ambos ejecutan por dispatcher, pero summary de Custom Tool es genérico |
| resultado de negocio (booking creado) | Debe verificarse con Scheduling y correlación de booking, no inferirse únicamente del “tool success” |

La evaluación de secuencia/argumentos/contexto requiere una interfaz de evidencia deliberada, redactada por defecto y limitada por schema. Nunca almacenar tokens, secretos, headers, PII innecesaria o resultados HTTP completos como evidencia genérica. Una futura evaluación puede usar fingerprints/campos allowlisted y resultado de negocio consultado por su owner.

## 11. Business Outcome Findings

**CONFIRMED:** existe dominio Scheduling para bookings y la capa Tools puede ejecutar `calendar.check_availability`/`calendar.create_booking`; CRM mantiene leads/actividades y contexto comercial; Notifications comunica hechos de booking. Estas son capacidades distintas y no equivalen a resultado de evaluación.

**INFERRED:** `appointment_booked` puede determinarse consultando Booking/Scheduling por relación/correlación segura; `lead_qualified`, `lead_converted`, `support_resolved`, `sale` o `payment_promise` no deben inferirse solo de transcript o tool success. No se verificó un catálogo unificado de outcomes ni todos los modelos para afirmar que esos outcomes estén ausentes.

**RECOMMENDED:** Evaluations guarda juicio/criterio y referencia a outcome externo; Scheduling es owner de reserva, CRM owner de estado de lead, y Billing owner de importes. Definir outcomes explícitos es follow-up de dominio, no crear ahora un catálogo especulativo.

## 12. CallSummaryService Analysis

`CallSummaryService` no pertenece puro a Analytics ni es una Evaluación. Es **composición de aplicación para CRM/Email**: resuelve lead con `CrmFacade`; prioriza latest CRM activity, luego Analytics `CallLookup.latest_summary`, luego CRM call context y el resumen actual del lead; crea un asset por `EmailFacade` y registra activity en CRM. También normaliza variables para usar el resumen en email.

No genera una evaluación, no mide score, no tiene rubric/evidence, y puede retornar summary CRM cuya procedencia y frescura difieren de Analytics. Mantenerlo donde esté durante PR #129. Si se desea moverlo después, primero separar orchestration de CRM/Email de lectura de facts Analytics mediante contracts, preservando el endpoint y la composición actual.

## 13. Current Dependency Graph

```text
Runtime ──HTTP contracts/events──> Voice Control Plane ──projection port──> Analytics
                                      │                                  └── Calls / CallEvents
                                      ├── public Agents boundary ──> Agent Builder versions
                                      ├── Tool public/runtime ports ──> Platform + Custom Tools
                                      │                                 └── Scheduling / CRM / Integrations
                                      └── VoiceSession + event ledger

CRM/email composition ──> CallSummaryService ──> CRM public + Analytics public + Email public
Billing ──> Analytics public usage facts
Scheduling ──> booking events / notifications pipeline
```

No formal Evaluations dependency edge exists in the inspected graph. Cycle risks: Analytics consuming Evaluation score for dashboards while Evaluations reads Analytics; Agents depending on rubric policies while Evaluations reads Agent config; CRM storing a copied evaluation result while Evaluations reads CRM outcomes. Evitar con Evaluations como consumidor y owner de resultados; downstream reporting puede consultar `evaluations.public`, pero no formar un ciclo de dominio. Outcomes se consultan mediante ports/adapters propiedad de CRM/Scheduling.

## 14. Proposed Evaluations Bounded Context

**Own:** `EvaluationDefinition`/immutable version, criteria/rubric snapshots, `EvaluationRun` identity/status, `EvaluationResult`, `CriterionResult`, evaluator provenance and evidence references, execution/retry state.

**Not own:** call facts/events, session lifecycle, transcript source of truth, tool execution, business booking/lead records, charges/cost ledger, agent configuration, runtime provider adapters, alerting/observability platform.

`BusinessOutcome evaluation` may be a criterion whose input is an owner-provided business fact; it is not ownership of the underlying booking/lead/outcome record.

## 15. Proposed Ownership Matrix

| Concepto | Owner actual | Owner propuesto | Acción |
|---|---|---|---|
| Call / CallEvent / metric snapshots | Analytics | Analytics | Keep; expose least-privilege DTO evidence query if needed |
| VoiceSession / events / transcripts received | Voice | Voice | Keep; add durable terminal event if absent |
| Agent identity/config/version | Agents | Agents | Keep; expose immutable version snapshot if missing |
| Tool invocation / execution | Tools | Tools | Keep; define redacted evidence DTO/correlation |
| Booking created/cancelled/rescheduled | Scheduling | Scheduling | Keep; expose tenant-scoped fact lookup/event |
| Lead qualification/conversion | CRM | CRM | Keep; clarify explicit outcome schema separately |
| Call summary | CRM/Email composition, with Analytics source | Composition service (current) | Keep in place for PR #129; no transfer |
| Evaluation definition/rubric/version | No formal owner found | Evaluations | New owned capability |
| Evaluation run/result/criterion result | No formal owner found | Evaluations | New owned capability |
| Cost / invoices / financial ledger | Billing | Billing | Keep; Evaluations may supply outcome count/query only |
| Dashboard/aggregate call metrics | Analytics | Analytics | Keep; consume evaluation facts through public boundary only if needed later |

## 16. Deterministic vs LLM Evaluators

| Family | Evaluator first choice | Existing evidence / gap |
|---|---|---|
| Terminal status, runtime/tool error, timeout | Deterministic | Session/call state and sanitized error events; timeout definition must be explicit |
| Tool call allowed/enabled and sequencing | Deterministic | Tool events lack durable args/result correlation; evidence contract needed |
| Correct arguments / trusted context / fixed config | Deterministic where schemas allow | Do not persist raw data by default; need allowlisted derived facts/fingerprints |
| Booking outcome | Deterministic | Scheduling fact lookup and correlation needed |
| Goal completion / role adherence / clarity / empathy | LLM judge or human review | Transcript + exact agent-version snapshot + rubric needed |
| Hallucination / unsupported claims / policy/compliance | LLM plus explicit deterministic policy checks/human escalation | Requires source-of-truth evidence and safety policy; do not treat judge output as truth |
| Latency / interruptions | Deterministic from timestamped turn/audio events | Uniform turn/audio event telemetry not confirmed |

Recommendation: ship deterministic evaluators before provider adapters; define `LlmEvaluatorPort` only when first concrete LLM criterion is in scope. Provider adapters belong in infrastructure. Domain/application must not import OpenAI, Anthropic, Ultravox, LiveKit or ElevenLabs SDKs.

## 17. Proposed Public Boundary

Make `app.modules.evaluations.public` import-light and ORM-free at the boundary, following Analytics. Minimal capabilities likely needed: `EvaluationRunner` (request/enqueue, not perform long LLM work inline), `EvaluationQueries` (read result by tenant/subject), and `EvaluationDefinitions` only if Agent Builder/admin needs definition management in this phase. A single `EvaluationFacade` can compose the first two; separate `EvaluationResults` and `BusinessOutcomeEvaluator` are unnecessary until distinct consumer contracts exist.

DTOs should express tenant, subject type/ID, definition/version, status, score/pass, safe reason/evidence references, evaluator type, provenance and timestamps. Public methods must derive tenant from trusted auth/application context at API edge; no frontend-supplied arbitrary tenant IDs.

## 18. Event / Async Processing Strategy

Reject synchronous LLM evaluation in call-finalization path. Preferred production pattern: terminal fact committed → durable outbox/domain event → worker claims and commits lease → reads evidence through ports → evaluates outside DB lock → stores result idempotently → marks event/result complete. Explicit QA evaluation request should call the same runner with a distinct source/idempotency key.

Existing Voice session events provide a ledger, but the reviewed evidence does not prove a universal outbox for terminal Voice state. First implementation must either reuse a verified durable event publisher or add a minimal outbox in Voice/application integration; do not silently make event publication best-effort if that can lose evaluations. At approximately 200 concurrent calls, cap worker concurrency, bound provider calls/timeouts, and retain backpressure/retry/dead-letter visibility. No provider/network I/O under row locks.

## 19. Idempotency Strategy

Use unique key `(tenant_id, subject_type, subject_id, definition_id, definition_version, trigger_key)` where `trigger_key` is stable source event ID for event-triggered jobs and explicit request ID for manual QA. If only one final run per definition-version-subject is allowed, omit trigger key and enforce that policy explicitly; retries update the existing run, not create duplicates.

Store source event ID and a hash/version of the canonical evidence snapshot. A retry with same identity but different evidence hash should be a conflict/reconciliation case, never silently overwrite a completed historical result. Use PostgreSQL unique constraints and `INSERT ... ON CONFLICT`/locked claim semantics; ensure tenant is in every lookup and uniqueness scope.

## 20. Multi-Tenant Invariants

- Every run, definition, result, evidence reference and worker claim is tenant scoped; system-owned definitions use explicit `owner_scope=system` and immutable published versions.
- API derives tenant from authenticated context; never trust request `tenant_id`.
- Composite constraints/FKs should ensure subject and definition belong to the same tenant where relationally possible; adapter verifies tenant on every external fact lookup.
- Evaluation of an agent session uses the immutable `agent_version_id` from that session; missing/ambiguous/cross-tenant resolution fails closed.
- Definition visibility is explicit (tenant or system); a tenant cannot mutate global definitions.
- Worker claim/event IDs are not authorization. All public reads re-check tenant ownership.
- Evidence minimization and redaction apply before persistence and logging; no raw secrets, authorization headers, full custom HTTP payloads, or unnecessary PII.

## 21. Versioning Strategy

Use immutable published `definition_version` snapshots. Editing a rubric creates a new version; run stores definition ID/version and snapshot/hash of criteria and evaluator configuration. Prompt template version and model/provider deployment identifier are provenance for an LLM criterion, not mutable definition aliases. A published definition version is never edited in place; historical results continue referencing the original version. Drafts may change without affecting queued/running runs, which pin version at enqueue time.

## 22. Explainability / Auditability

Persist criterion ID/version, score/pass/normalized outcome, short evidence-backed reason, evidence references or bounded excerpts, evaluator type (`deterministic`, `llm`, `human`), evaluator implementation version, model ID where relevant, prompt version, evaluated timestamp and evidence snapshot hash. Keep evidence minimization, access controls and retention rules. Do not store private chain-of-thought; ask judge for concise rationale tied to supplied evidence and return structured outputs validated against schema. Preserve raw input only where lawful, necessary, and already governed by owning module.

## 23. Cost-per-Outcome Integration

Viable only when numerator and denominator share tenant, period, currency/units, and outcome definition. Billing owns financial amounts/ledger; Analytics supplies call usage facts (currently billed minutes); Telephony/provider usage may be another cost component; Scheduling/CRM own outcome facts; Evaluations may define the qualifying evaluated outcome or provide counts. Do not calculate financial truth inside Evaluations and do not assume minutes equal total AI + telephony cost. Publish an aggregate/query contract later, with handling for zero outcomes and incomplete cost windows.

## 24. PostgreSQL Concurrency Requirements

Before merge, PostgreSQL integration tests should cover: concurrent creation for identical run identity; duplicate event/request delivery; lease claim by two workers (`FOR UPDATE SKIP LOCKED`); claim expiry and stale owner unable to complete newer claim; transaction commit before evaluator/provider I/O; tenant isolation on subject/definition/result queries; immutable definition-version snapshot during concurrent publish/edit; concurrent criterion result inserts and unique criterion identity; retry after transient failure; late result rejected after run superseded/cancelled; evidence hash conflict behavior; result completion atomic with worker state. SQLite is not sufficient for lock/isolation semantics.

## 25. Architecture Gates

- No imports of `app.modules.evaluations.domain/application/infrastructure` from other modules; consumers import `.public` only.
- Evaluations domain/application cannot import ORM models, SQLAlchemy, provider SDKs, Voice/Analytics/CRM/Scheduling internals.
- No cross-module ORM relationships or direct foreign keys into another module's owned table unless repository policy explicitly permits a stable reference; prefer opaque IDs plus public lookup.
- Static import tests verify public boundary import does not load SQLAlchemy.
- Contract tests verify tenant-scoped DTOs, no raw tool payload/credentials, and stable OpenAPI where no endpoint contract change is intended.
- Dependency graph gate rejects cycles involving Evaluations ↔ Analytics/CRM/Agents.

## 26. Contract Risks

- Terminal Voice events and runtime payloads may be consumed by new worker; preserve current event IDs, statuses and runtime schema.
- `CallEventView` intentionally omits payload; exposing it to Evaluations is a new public capability and privacy/contract decision.
- Tool event payloads intentionally omit raw arguments/results; adding them would raise security, PII and retention risk.
- Adding evaluation API endpoints changes OpenAPI; separate from any ownership-only groundwork and record exact baseline diff.
- Reusing QA endpoint behavior must not change session creation, transport/token flows, or CRM context trust boundary.
- New tables/migrations are likely for durable definitions/runs/results/outbox only if no existing durable queue is suitable; no existing table migration is justified by discovery.
- No observed reason to change Billing, Analytics, CRM, Agent Builder, or voice provider contracts in the first PR.

## 27. Proposed Migration Sequence

1. **Ownership/domain contracts:** skeleton, immutable definition/run/result DTOs and deterministic evaluator; no cross-module reads.
2. **Persistence:** add only required Evaluations tables and constraints; compare DDL baseline and run PostgreSQL concurrency tests.
3. **Public boundary:** import-light facades and tenant-safe query/request contracts.
4. **Evidence adapters:** consume Voice/Analytics/Tools/Agents/Scheduling via public DTOs; add missing minimal public capability only when evidence proves necessary.
5. **Durable trigger/worker:** verified outbox/domain event, claim/lease/retry, no provider I/O under lock; explicit QA request uses same path.
6. **Legacy consumer integration:** only identified evaluation-like consumer if one is found; retain existing summary/CRM behavior.
7. **Runtime/QA integration:** enqueue on terminal session and expose result separately; preserve existing QA event UI contract.
8. **Architecture gates + PostgreSQL tests:** dependency direction, isolation, idempotency, worker semantics.
9. **Docs, DDL/OpenAPI comparison, final audit:** update canonical docs only for finalized contracts/operations; remove legacy evaluator only if discovery finds one and behavior is preserved.

This differs from the suggested 9-commit sequence by delaying adapters/legacy removal until the core owner and persistence are proven, and by introducing durable async triggering before production runtime integration.

## 28. PR #129 Scope

**IN SCOPE (recommended minimum):** create the Evaluations bounded context and public boundary; immutable definition version and run/result persistence; one or two deterministic criteria derived from existing terminal/tool facts; tenant-scoped idempotent enqueue; durable asynchronous worker/claim semantics; evidence DTO adapters via public boundaries; PostgreSQL concurrency and architecture tests; docs and DDL/OpenAPI diffs.

**Conditional in scope:** minimal terminal Voice trigger and QA manual trigger, only after confirming an existing durable outbox/event mechanism or agreeing to add the smallest safe one.

## 29. Out of Scope

Full Observability/alerting/tracing replacement, broad rubric authoring UI, provider migrations, LLM judge adapters/prompts/model selection, full cost model, new CRM workflows/outcome catalog, changes to Booking or call lifecycle semantics, raw transcript/tool payload warehouse, load testing infrastructure, and removal/refactor of `CallSummaryService`.

## 30. Technical Debt

| Class | Finding | Treatment |
|---|---|---|
| BLOCKER for production evaluator | Remote branch freshness not verified; durable terminal event/outbox behavior not established | Resolve before coding/merging on current branch |
| BLOCKER for production evaluation breadth | Uniform transcript/tool evidence contract and retention/privacy policy not established | Limit v1 to deterministic facts or define explicit evidence DTO first |
| FOLLOW-UP | Analytics public evidence query omits call event payload and does not expose a unified evaluation snapshot | Add only a least-privilege capability if required |
| FOLLOW-UP | Custom tool success telemetry is generic and invocation correlation is not uniform | Improve owned Tools evidence contract separately or in narrow adapter work |
| LEGACY | `CallSummaryService` composes CRM activity/context/lead, Analytics summary, and Email asset behavior | Preserve; refactor only under separate scope |
| OUT-OF-SCOPE | Full business outcome catalog and financial cost-per-outcome model | Separate domain/finance initiatives |

## 31. Proposed Acceptance Criteria

- Ownership and public dependency rules documented and enforced.
- Evaluation definitions are immutable/versioned; historical run pins exact version/evidence hash.
- Deterministic evaluator creates explainable criterion results without provider dependency.
- Run creation is idempotent under duplicate events/retries and tenant scoped at DB and API boundaries.
- Async worker uses PostgreSQL-safe claims/leases, stale-owner protection and provider I/O outside locks.
- QA and production can request evaluation without blocking session completion; existing QA/runtime behavior remains unchanged.
- Cross-tenant subject/definition/result access fails closed; missing/ambiguous agent version fails closed.
- Evidence contains only approved/redacted fields; no chain-of-thought, secrets or unnecessary PII.
- PostgreSQL concurrency tests and architecture gates pass.
- DDL and OpenAPI baselines are compared; any changes are expected and documented.
- CI, lint, typecheck, build and scoped backend suites pass under the project’s current Sprint rules before the eventual implementation merge.

`LLM evaluator port`, `business outcome catalog`, `tool-argument correctness`, and cost-per-outcome are not minimum closure requirements for the first PR unless the agreed product acceptance explicitly requires them.

## 32. Recommended Next Action

Restore permission to update/fetch `origin/develop`, confirm HEAD and clean status, then perform a focused second lexical inventory for evaluation/score/sentiment/outcome/rubric/judge and inspect current Alembic/outbox/event publisher contracts. Review this report and approve a concrete PR #129 scope before implementation. **No implementation should start from this local snapshot alone because remote freshness and two key evidence capabilities remain unverified.**

### Evidence and commands used

**CONFIRMED commands/results:**

```text
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch
git remote get-url origin
git log -1 --oneline
git pull --ff-only  # attempted; failed: permission denied writing .git/FETCH_HEAD
```

**CONFIRMED CodeGraph discovery:** status, searches for `CallSummaryService`, tool dispatcher/executor, Analytics public classes, Call/CallEvent, summary/outcome terms; two `codegraph_explore` calls; symbol/context lookups for Voice session service/model/events, QA Harness, Agent versions, Analytics contracts/facades, Scheduling booking service. Additional source reads were limited to files CodeGraph listed as relevant additional files. No test or migration command was run.

**INFERRED:** absence claims are limited to formal capabilities not found in the indexed symbols/selected source; broad lexical negatives should be reconfirmed with the follow-up `rg` pass after the branch is synchronized.
