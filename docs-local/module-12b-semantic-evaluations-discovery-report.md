# Module 12B — Semantic Evaluations Discovery Report

Fecha: 2026-10-08
Checkout: develop, origen https://github.com/ServiAi/servoglobal-voice
Base verificada: 7fc4019, merge de PR #129
Alcance: discovery y diseño; sin implementación

## 1. Executive Summary

- CONFIRMED — develop está limpio y al día con origin/develop; HEAD contiene el merge 7fc4019 de PR #129.
- CONFIRMED — Evaluations Core ya tiene definiciones/versiones inmutables, runs idempotentes, snapshots JSON con hash, cola PostgreSQL, claims con lease, generaciones y protección de stale workers. El evaluador disponible hoy es determinístico y de technical health.
- CONFIRMED — Voice produce eventos voice.transcript.final con user/assistant, texto y secuencia; RuntimeEventIngestor valida y persiste el payload permitido en voice_session_events. Analytics consume los mismos hechos.
- CONFIRMED — no existe actualmente un reader público de transcript para otros módulos, ni una capability pública de Agents que entregue el snapshot histórico mínimo para un juez.
- CONFIRMED — la búsqueda de dependencias/configuración no encontró SDK ni abstracción general de LLM para OpenAI, Anthropic, Google/Gemini u OpenRouter. El registro y las credenciales existentes son específicos de Voice.
- RECOMMENDED — mantener Voice como owner del transcript y Agents como owner de la versión del agente. Exponer readers read-only, tenant-scoped y DTO-based por sus límites public.
- RECOMMENDED — una definición semantic separada de la technical evita que fallas y retries de proveedor alteren resultados determinísticos.
- BLOCKER — no hay redacción de transcript confirmada ni garantía de que todos los eventos finales hayan llegado al almacenarse el estado terminal. No enviar PII cruda a un proveedor ni declarar el transcript completo hasta resolver estas dos condiciones.
- RECOMMENDED — no elegir un proveedor aún. Primero definir un port y comparar proveedores con criterios verificables de structured output, privacidad, residencia, coste, timeouts e idempotencia. Usar credenciales gestionadas por plataforma en la primera versión.
- RECOMMENDED — se requiere DDL aditivo para representar insufficient_evidence y guardar provenance. Los campos actuales de CriterionResult no bastan para ese contrato.

## 2. Current Evaluations Core State

CONFIRMED — app.modules.evaluations existe en backend/app/modules/evaluations y se expone mediante app.modules.evaluations.public. La superficie pública incluye EvaluationRunner, EvaluationQueries, EvaluationFacade, VoiceSessionEvidence y ToolOutcomeEvidence.

CONFIRMED — backend/app/modules/evaluations/infrastructure/models.py define EvaluationDefinition, EvaluationDefinitionVersion, EvaluationRun y CriterionResult. Las versiones publicadas no se pueden mutar; criteria_json es JSON y el run conserva definition_version_id.

CONFIRMED — EvaluationRun ya ofrece status queued/running/completed/failed/cancelled, evidence_hash, evidence_json, tenant_id, agent_version_id, claim_token, claim_generation, lease_expires_at, attempt_count, passed nullable y score. Su identidad única incluye tenant, subject, versión de definición y trigger.

CONFIRMED — CriterionResult conserva criterion_key, evaluator_type (deterministic/llm/human), implementation_version, passed boolean no nullable, score opcional 0–100, razón de hasta 500 caracteres y evidence_ref_json.

CONFIRMED — backend/app/modules/evaluations/infrastructure/repositories.py reclama con FOR UPDATE SKIP LOCKED; commits claims, limita a cinco intentos, protege completions por token/generación/lease y guarda resultados atómicamente. El executor actual evalúa el snapshot técnico dentro de su sesión de DB. Una futura llamada de red debe aislarse expresamente de esa transacción.

CONFIRMED — el pipeline terminal de Voice en backend/app/modules/voice/wiring.py crea VoiceSessionEvidence y solicita la definición system voice_session_technical_health. La evidencia actual contiene datos terminales y resúmenes de resultados de tools, no transcript ni configuración de agente.

CONFIRMED — backend/test_evaluations_postgres.py cubre idempotencia/hash conflict, claims concurrentes, protección stale, retry acotado, atomicidad y tenant isolation. La prueba exige PostgreSQL dedicado mediante EVALUATIONS_TEST_DATABASE_URL.

## 3. Transcript Pipeline

CONFIRMED — voice-runtime/src/serviglobal_voice_runtime/providers.py escucha conversation_item_added. Acepta roles user y assistant, omite items interrumpidos, vacíos o no textuales, incrementa transcript_sequence y emite voice.transcript.final con source livekit, sequence y speaker/text.

CONFIRMED — el envío de cada transcript se programa con asyncio.create_task. La secuencia se asigna antes del envío, pero no hay prueba de que las tareas terminen en orden o antes del cierre de sesión.

CONFIRMED — el cliente de runtime envía eventos al control plane; backend/app/modules/voice/application/runtime_events.py filtra payload a ALLOWED_PAYLOAD_KEYS, valida transcript final (speaker, texto no vacío y máximo 10.000 caracteres) y usa VoiceSessionService.record_event para persistirlo.

CONFIRMED — backend/app/modules/voice/infrastructure/models.py almacena eventos en voice_session_events: event_id único (80 caracteres), tenant_id, voice_session_id, event_type, source, sequence nullable, payload_json, occurred_at y created_at. Hay índices por tenant/session y session/created_at.

CONFIRMED — el runtime asigna un UUID nuevo al construir cada RuntimeEventV1 en voice-runtime/src/serviglobal_voice_runtime/control_plane.py; VoiceSessionEvent usa ese event_id y RuntimeEventIngestor descarta duplicados. La deduplicación existe para reenvíos del mismo evento, aunque no se identificó una clave estable para regeneraciones semánticamente duplicadas del mismo turno.

CONFIRMED — backend/app/modules/analytics/application/projection_service.py ordena turnos por sequence cuando existe, y luego occurred_at/event_id; transforma eventos finales en hechos para la proyección CRM. Esto demuestra que los dos roles se consideran, no que Analytics sea el source of truth.

CONFIRMED — backend/app/modules/voice/api/router.py filtra campos de transcript para la respuesta de eventos QA. Esa ruta es una API de QA autenticada, no un límite interno público adecuado para el módulo Evaluations.

INFERRED — no hay garantía de completitud al alcanzar estado terminal. No se halló marcador de transcript-complete, barrera de drenaje de tareas, conteo esperado ni reconciliación antes de encolar la evaluación. La emisión asíncrona puede competir con el cierre.

CONFIRMED — no se identificó una ruta de transcript parcial en la evidencia buscada; el camino inspeccionado emite eventos finales. No se concluye que ningún provider futuro pueda producir parciales.

## 4. Transcript Source of Truth

RECOMMENDED — Voice conserva la propiedad de VoiceSessionEvent y de los hechos del transcript. Evaluations debe pedir un DTO a voice.public y no consultar voice_session_events ni VoiceSession directamente.

RECOMMENDED — añadir una capability equivalente a VoiceConversationEvidenceReader: lectura por tenant_id + session_id, sólo en sesiones terminales, orden estable, event_ids validados, status terminal y metadata de completitud. La consulta debe ser read-only y no devolver ORM.

BLOCKER — antes de habilitar juzgado semántico, definir una garantía de transcript complete. Alternativas a evaluar en implementación: barrera de secuencias/drenaje en runtime, evento final de transcript con contadores, o política explícita de ventana de estabilización con reconciliación. La estrategia debe cubrir pérdida y duplicación de eventos.

## 5. AgentVersion Evidence

CONFIRMED — VoiceSession fija agent_version_id al crear la sesión usando AgentsFacade.lock_published_agent. La versión se trata como inmutable durante la sesión; backend/app/modules/voice/infrastructure/models.py sólo permite soltarla al borrar/desvincular el agente terminal y conserva entonces deleted_agent_version_id.

CONFIRMED — TenantAgentVersion contiene tenant_id, version, status, language, identity_json, instructions_json, behavior_json y runtime_binding_json. La sesión no conserva un snapshot completo de estos documentos.

CONFIRMED — AgentsFacade.compile_runtime_spec requiere un version_id explícito y compila esa versión, no la latest. No es el contrato de evaluación mínimo: incluye contexto/runtime y está orientado a ejecución de Voice.

CONFIRMED — app.modules.agents.public no expone un snapshot semántico de versión. AgentsFacade ofrece estado, bindings, display y compilación de runtime; no devuelve el conjunto mínimo role/objective/system_prompt/greeting/closing/reglas.

CONFIRMED — TenantAgentVersion está en infraestructura de Agents y se elimina en cascada con el agente; VoiceSession.agent_version_id usa SET NULL. Por tanto, el identificador histórico puede dejar de resolver después de borrar el agente.

RECOMMENDED — crear AgentEvaluationSnapshotReader en agents.public, tenant-scoped y read-only, que requiera agent_version_id exacto y devuelva identidad/instrucciones/comportamiento necesarios, language y bindings seleccionados ya sanitizados. No exponer runtime ORM, secretos ni credenciales. Si la versión ya no existe, fallar con código seguro o utilizar un snapshot inmutable retenido por política explícita; nunca consultar la versión actual.

## 6. Existing LLM / Model Provider Infrastructure

CONFIRMED — no se encontró abstracción LLM general, chat completion, structured generation ni registry de modelos de evaluación en backend. Las dependencias backend/requirements.txt y voice-runtime/pyproject.toml no incluyen SDKs de OpenAI, Anthropic, Gemini, OpenRouter, Instructor o LiteLLM.

CONFIRMED — backend/app/modules/voice_providers/domain/registry.py define providers/modelos para Voice realtime; los únicos modelos disponibles inspeccionados son Ultravox. OpenAI, Google y Anthropic figuran como planned, no como adapters LLM de evaluación.

CONFIRMED — voice-runtime depende de LiveKit Agents y livekit-plugins-ultravox, que no constituyen un port de judge para Evaluations. No reutilizar ese registry como catálogo semántico.

RECOMMENDED — interfaz del juez propia del módulo Evaluations, con adapters aislados bajo infrastructure. El primer adapter puede usar httpx ya presente en backend, si el proveedor elegido ofrece un endpoint compatible; no añadir SDK hasta demostrar que aporta validación o soporte que el cliente existente no cubra.

## 7. Existing Credentials Infrastructure

CONFIRMED — Voice Provider guarda configuración tenant-scoped cifrada en TenantVoiceProviderConfig y expone ProviderCredential en memoria para una sesión. El resolver exige proveedor asociado a la sesión; estas credenciales pertenecen a Voice Provider, no a Evaluations.

CONFIRMED — no se encontró un almacén genérico de credenciales LLM para evaluación ni credencial global de judge ya configurada.

RECOMMENDED — plataforma gestiona las credenciales del juez en secret/config deployment durante 12B; los tenants no aportan BYOK al inicio. El adapter las resuelve fuera de EvaluationDefinitionVersion, EvaluationRun, CriterionResult y AgentVersion. Esta decisión evita acoplar calidad/resultado a claves particulares de cada cliente. Si se introduce BYOK, hacerlo como feature separada con control de acceso, cifrado, rotación, auditoría y aislamiento definidos.

## 8. Semantic Evidence Contract

RECOMMENDED — DTO inmutable versionado, no ORM, aproximadamente:

- tenant_id, session_id, purpose, terminal_status, ended_at.
- agent_version_id y AgentEvaluationSnapshot exacto.
- idioma de sesión si se establece explícitamente; si no existe, agent language y language_detected sólo como facts distintos y opcionales.
- conversation_turns ordenados: event_id, sequence nullable, speaker enum, text redacted, occurred_at.
- tool outcome summaries existentes, sin argumentos ni payloads completos.
- evidence_version, evidence_hash, completeness state y redaction version.
- referencias al source Voice y AgentVersion, sin secretos.

CONFIRMED — tenant_id, session_id, purpose/status, ended_at, agent_version_id y tool outcome están ya disponibles en VoiceSessionEvidence; el transcript DTO, language de sesión, snapshot del agente y completitud no están en el contrato actual.

RECOMMENDED — normalizar con sequence primero; los eventos sin secuencia se ordenan por occurred_at y event_id y se marcan como menor confianza. Rechazar event_id duplicados con payload conflictivo. Limitar caracteres/tokens antes de llamar al proveedor.

## 9. Privacy / PII Assessment

CONFIRMED — el texto libre de participantes puede contener nombres, teléfonos, emails, direcciones, números de documento, información financiera o salud. El código conserva el texto final y el QA payload permite el texto; no se encontró redactor de transcript aplicable a esta ruta.

RECOMMENDED — no mandar transcript raw a provider en producción hasta disponer de redaction policy y adapter verificable. Introducir TranscriptRedactionPort como capability independiente que devuelva texto redactado más mapa/versión de redacción sin retener el texto original en logs.

RECOMMENDED — persistir únicamente hash, refs y la evidencia redactada mínima necesaria para auditoría bajo retención definida. La evidencia JSON actual puede guardar snapshots, pero no debe convertirse en una segunda copia permanente de transcript sin política de retención/borrado. Si sólo se guardan refs, reproducibilidad depende de que Voice conserve eventos y Agent conserve la versión durante el periodo de auditoría.

INFERRED — reproducibilidad exacta y borrado no pueden garantizarse simultáneamente sólo con IDs si el owner elimina la fuente. La política de retención y derecho de borrado debe determinar qué evidencia redactada se conserva y por cuánto tiempo.

## 10. Prompt Injection Threat Model

RECOMMENDED — toda conversación, prompt de agente y tool summary deben entrar como datos no confiables dentro de un envelope estructurado; nunca interpolarlos como instrucciones de sistema. El prompt del judge debe indicar que evalúe el transcript, ignore órdenes que aparecen dentro de él y no siga enlaces.

RECOMMENDED — el juez no recibe tools ni navegación, no ejecuta código, no llama URLs ni consulta CRM. Capacidad única: evidencia redactada de entrada, juicio JSON de salida.

RECOMMENDED — separar role/system/developer policy del campo transcript; delimitar cada turno con speaker + id y serialización JSON segura. Structured output reduce errores de formato, pero no demuestra por sí sola resistencia a prompt injection. Validar evidencia devuelta contra los IDs suministrados.

RECOMMENDED — añadir casos adversariales con transcript que exige score máximo, intenta revelar prompts, o pide enviar datos fuera del sistema. Evaluar el contenido como habla del participante, nunca como instrucción del judge.

## 11. Proposed Semantic Criteria

RECOMMENDED — rubric versionada por criterio, con definición operacional, evidence required, categorías de verdict, límites de score y criterio de insufficient_evidence.

RECOMMENDED — empezar con goal_completion, instruction_adherence y conversation_quality, evaluados independientemente sobre el mismo snapshot redactado. Evitar un atributo combinado “calidad general” que esconda causas.

## 12. Goal Completion Design

RECOMMENDED — juzgar si el objetivo de la versión exacta del agente se completó en la conversación. Salidas: achieved, partially_achieved, not_achieved, insufficient_evidence. El objetivo debe estar presente y no vacío.

RECOMMENDED — el transcript respalda lo que se dijo, no prueba un resultado de negocio. El criterio debe decir “la conversación parece completar el objetivo” y no “el booking existe”. Para booking, lead creado o pago, usar facts verificados de Scheduling/CRM/Tools cuando exista un public port.

## 13. Instruction Adherence Design

RECOMMENDED — evaluar role, system instructions y behavioral constraints de AgentVersion fijada, distinguiéndolos explícitamente de lo que pide el caller. Citar turn IDs de evidencia positiva/negativa; no premiar obediencia a instrucciones adversariales del transcript.

RECOMMENDED — tratar instrucciones del agente que estén ausentes o contradictorias como configuration_missing/insufficient_evidence, no inventar una política a partir de la conversación.

## 14. Conversation Quality Design

RECOMMENDED — rubric pequeña y observable: claridad, relevancia, coherencia entre turnos, repetición innecesaria y cierre apropiado cuando la sesión termina tras conversación suficiente.

RECOMMENDED — excluir personality, likability y charisma. No penalizar falta de cierre en sessions failed/cancelled antes de que hubiera intercambio sustantivo.

## 15. Rubric Versioning

CONFIRMED — criteria_json es una lista JSON y EvaluationDefinitionVersion publicada es inmutable. El Core soporta fijar versión de rubric por definition version sin tabla nueva.

RECOMMENDED — cada criterio incluye key, evaluator_type, rubric_version, threshold, score scale y parámetros estructurales validados. No guardar prompt libre ni secretos dentro de criteria_json. Una nueva rúbrica publica una nueva EvaluationDefinitionVersion; no editar versiones pasadas.

## 16. Prompt Versioning

RECOMMENDED — prompts iniciales como assets versionados en código, identificados por prompt_key, prompt_version y SHA-256 calculado del contenido canónico. Persistir dichos valores en provenance por resultado.

RECOMMENDED — el worker debe resolver el prompt exacto indicado por la versión de la definición; jamás usar latest al ejecutar un run histórico. Cambio del prompt requiere nueva versión de definition/configuración o un mapping inmutable.

## 17. Structured Output Contract

RECOMMENDED — modelo tipado Pydantic SemanticJudgeResult con criterion_key, verdict enum, score band, reason breve y evidence_turn_ids. Validar límites, valores enum, score/verdict consistency, longitud de razón y que IDs existan en la entrada.

RECOMMENDED — JSON inválido, campo extra crítico, JSON truncado, event_id inventado o score/verdict inconsistente producen error seguro; no intentar extraer una respuesta de texto libre. No guardar chain-of-thought.

## 18. Provider / Model Provenance

CONFIRMED — CriterionResult no tiene provider/model/prompt/schema/latency/usage fields; evidence_ref_json representa refs de evidencia y no debe asumir esa semántica.

RECOMMENDED — campo provenance_json aditivo y acotado en CriterionResult (o metadata de ejecución normalizada si el provider/model son comunes a todo el run). Registrar provider, model solicitado y resuelto, model revision si existe, prompt key/version/hash, evaluator implementation version, schema version, evaluated_at, latency y tokens reportados. Nunca registrar credencial, prompt completo o transcript.

RECOMMENDED — guardar tokens/usage como hechos del provider. Dejar el cálculo financiero a Billing.

## 19. Proposed LlmJudgePort

RECOMMENDED — port de aplicación en términos propios:

- evaluate(request: SemanticJudgeRequest) -> SemanticJudgeResponse.
- request incluye evidence version/hash, turns redactados, snapshot de agente, criterio/rubric/prompt version, output schema version, límites y timeout.
- response contiene resultado estructurado y usage/provenance neutralizados.
- errores tipados: timeout, rate_limited, unavailable, invalid_output, configuration_error. Sanitizar errores provider y nunca propagar headers/cuerpo/secreto.
- no provider DTO/SDK cruza al dominio/application.

RECOMMENDED — adapter síncrono puede ser suficiente para el worker actual, pero debe usar timeout estricto y cancelar la request si vence.

## 20. Recommended First Provider

CONFIRMED — el repositorio no tiene adapter LLM, modelo semántico, credencial judge ni structured-output integration. OpenAI/Google/Anthropic están sólo como entradas planned en un catálogo de Voice y no son evidencia de aptitud para evaluation.

RECOMMENDED — no seleccionar proveedor en esta fase. Mantener provider-neutral port y hacer una qualification spike comparativa con proveedores elegibles: JSON schema estricto, retención/no-training, región y residencia de datos, disponibilidad, coste por token, límite de contexto, timeout, rate limits, idempotency support y términos de datos. Elegir el primer adapter sólo tras esa evidencia y aprobación del plan.

INFERRED — httpx ya es dependencia backend y basta para un adapter HTTP básico, así que no hay razón demostrada para instalar un SDK antes de seleccionar proveedor.

## 21. Async Worker Integration

CONFIRMED — backend/app/modules/evaluations/runtime/worker.py ya usa worker PostgreSQL, claim batch de 25, lease de 60 segundos y un DB session por ejecución. Las constantes no son aún adecuadas por evidencia para latencia de proveedor.

RECOMMENDED — compartir cola/runtime pero tener una semantic EvaluationDefinition distinta. El run técnico sigue usando el snapshot terminal liviano; el run semántico sólo se encola cuando transcript completeness, agente histórico y redaction están disponibles.

RECOMMENDED — el runner carga refs/evidencia, cierra la transacción de lectura, invoca judge, valida salida y abre una nueva transacción para persistir. Si necesita persistir una fase de preparación, hacerlo en una transacción previa corta.

## 22. Transaction Boundary Analysis

CONFIRMED — claim_batch comitea el lease antes de ejecutar. En Core actual, repository.execute carga y evalúa usando su Session; evaluación determinística no hace I/O remoto.

RECOMMENDED — para semantic: TX 1 claim/commit; lectura de fuentes en transacción corta y cierre; llamada LLM sin transacción; TX 2 lock del run, comprobar tenant/status/token/generation/lease y persistir resultados/provenance o error. La sesión SQLAlchemy no debe quedar abierta durante el POST aunque no sostenga locks.

RECOMMENDED — revisar si Database session puede cerrarse y reabrirse entre fases conservando sólo DTOs; no pasar un ORM object a un provider adapter.

## 23. Lease / Timeout Strategy

CONFIRMED — el worker usa lease de 60 segundos y no tiene heartbeat/renewal. La duración de proveedor aún no existe.

RECOMMENDED — establecer provider timeout significativamente menor que el lease (por ejemplo, timeout 20 s y lease 60–90 s inicialmente, sujeto a medición), con margen de validación y commit. Si proveedor no ofrece timeout total estrictamente acotado, bajar timeout o implementar renovación tras prueba que la requiera.

RECOMMENDED — no agregar heartbeat para v1 si timeout estricto más margen demuestra que cada intento termina antes del lease. Un completion posterior al lease siempre se descarta por token/generation/lease.

## 24. Retry Strategy

RECOMMENDED — retry bounded con backoff y jitter para timeout, 429 y fallas transitorias 5xx; máximo bajo y configurable. Respetar Retry-After dentro de límites.

RECOMMENDED — invalid JSON/schema/evidence ID, credentials/configuration errors, evidence missing/incomplete y prompt config errors son non-retryable hasta que cambie la entrada/configuración. No retries infinitos ni corregir el resultado por heurística.

RECOMMENDED — crear failure codes sanitizados y medir cada clase; no guardar respuesta cruda del proveedor en logs.

## 25. Sampling / Enablement Strategy

RECOMMENDED — configuración de evaluación, no runtime del Agent. QA puede solicitar semantic run explícito con 100% al pasar gates de privacy/completeness. Producción empieza disabled-by-default con sampling configurable por tenant policy en tabla/policy de evaluaciones, no AgentVersion.

RECOMMENDED — definir hash-based deterministic sampling a partir de tenant/session/definition version para evitar sesgo por reintentos. Registrar elegibilidad y motivo de exclusión sin PII. No iniciar producción hasta fijar presupuesto y límites.

## 26. Multi-Tenant Invariants

RECOMMENDED — el tenant se obtiene de VoiceSession dentro de Voice reader, no de un campo arbitrario del payload del worker. Cada reader exige tenant_id + session_id y filtra ambos en la misma consulta.

RECOMMENDED — Agents reader exige el mismo tenant_id y agent_version_id exacto, comprobando la pertenencia de versión. No resuelve ids sin tenant scope.

CONFIRMED — EvaluationRun y CriterionResult ya tienen filtros/constraints tenant-aware; las pruebas PostgreSQL ejercitan rechazo de tenant inconsistente. Extender las pruebas a transcript y agent snapshots cross-tenant.

## 27. Security Invariants

RECOMMENDED — read-only DTO boundaries; ninguna infraestructura/ORM de Voice/Agents importada por Evaluations; sin herramientas ni navegación; redactar antes del provider; limitar input/output; sanitizar errores; no registrar transcript, API key, Authorization header ni provider body.

RECOMMENDED — si una referencia de evidencia no pertenece al snapshot suministrado, rechazar el resultado completo. La validación es cerrada.

## 28. DDL Impact

CONFIRMED — criteria_json puede representar criterio llm y las versiones publicadas son inmutables. EvaluationRun ya almacena evidencia JSON y hash; voice_session_semantic_quality puede crearse como definición distinta sin nuevas tablas de rubric.

CONFIRMED — CriterionResult.passed es NOT NULL y no tiene outcome/status; por tanto, no representa insufficient_evidence explícitamente. EvaluationRun.passed ya es nullable, pero eso no reemplaza el estado por criterio.

RECOMMENDED — DDL aditivo mínimo: outcome/status nullable o enum/string controlado en CriterionResult, permitir passed nullable para semántica insuficiente, y provenance_json nullable/default {}. Conservar score 0–100 y usar bandas rubricadas; score/passed/outcome deben tener una regla inequívoca. No alterar comportamiento del evaluator determinístico existente.

RECOMMENDED — preferir cambio nullable/additive y constraints que acepten resultados históricos. No añadir tablas de prompt/provider salvo que policy de retención o multi-tenant configuración requiera ownership persistente.

## 29. OpenAPI Impact

CONFIRMED — el endpoint actual de Voice events es QA/controlado y no hay API de Evaluation admin en el alcance descrito.

RECOMMENDED — OpenAPI sin cambios para el primer PR; consumo interno por public facades y worker. No UI ni endpoints de administración hasta que haya requisito de producto.

## 30. PostgreSQL Test Requirements

RECOMMENDED — usar PostgreSQL real para claim/retry de semantic, lease expiry durante llamada, stale completion, idempotent duplicate request, evidencia/provenance persistida atómicamente, tenant isolation en ambas readers, definición mixta si se prueba, constraint para insufficient_evidence y compatibilidad con filas históricas.

RECOMMENDED — fake judge determinístico en suite normal; no provider real en CI. Smoke provider manual separado y exactamente una llamada por ejecución manual billable.

## 31. Architecture Gates

RECOMMENDED — tests que aseguren que Evaluations domain/application no importa SDK ni Voice/Agents infrastructure; wiring importa únicamente voice.public/agents.public; no ORM cruza módulo; no credenciales en modelos; los adapters viven en infrastructure; la llamada externa ocurre después de commit del claim.

RECOMMENDED — architecture/domain test: una sesión fijada a v3 se evalúa con v3 cuando el agente actual es v7. Si v3 fue borrada, resultado controlado de evidence missing; nunca fallback a latest.

## 32. Proposed Dependency Graph

RECOMMENDED —

Voice terminal facts/transcript → voice.public VoiceConversationEvidenceReader
AgentVersion exacta → agents.public AgentEvaluationSnapshotReader
ambos DTO → Evaluations evidence canonicalizer/redactor → SemanticEvaluator
SemanticEvaluator → LlmJudgePort → provider adapter en Evaluations infrastructure

Voice/Agents no dependen de provider adapter; no se forma ciclo. Evaluations ya se solicita desde Voice para technical health; separar la petición semántica por policy y definición mantiene el acoplamiento unidireccional.

## 33. Proposed Implementation Sequence

1. 12B.1 — evidencia pública e integridad: acordar completitud de transcript, Voice reader, Agent snapshot reader, tenant scope, redaction/privacy gate y hashes; tests contract/architecture.
2. 12B.2 — datos y evaluación semántica: nueva definición/version rubric, outcomes + provenance aditivos, evaluator y FakeLlmJudge; golden fixtures locales y pruebas PostgreSQL.
3. 12B.3 — provider qualification + adapter: seleccionar tras spike aprobada, secrets platform-managed, límites/retries/observabilidad y manual smoke.
4. 12C — datasets, regression lab y comparisons.

RECOMMENDED — no combinar todo el alcance en un PR. El primer PR debe entregar evidence contracts y readers sin llamadas billables. El segundo añade la semántica fake y DDL. El tercero integra un provider tras su selección.

## 34. PR Scope

RECOMMENDED — un solo PR sería demasiado amplio para entregar evidence retention/privacy, dos boundaries, provider adapter, tres rubrics, provenance, worker semantics y PostgreSQL invariants con revisión segura.

RECOMMENDED — mínimo primer PR de implementación: Voice/Agents public readers, DTOs versionados, completitud de transcript, tests cross-tenant/versión histórica y gates de privacidad; no llamadas LLM, no API pública, no UI. Antes de empezar, decidir si la primera entrega puede usar QA/sintético o si redaction completa es requisito bloqueante.

## 35. Out of Scope

RECOMMENDED — quedan fuera inicialmente: full hallucination detection, knowledge-grounded evaluation sin grounding formal, compliance engine, human review UI, rubric builder, dashboard/comparación de agentes, coste por outcome, prompt optimization/mutación automática, alerting, observability module, dataset management, A/B testing, fact verification de booking/CRM y billing.

RECOMMENDED — clasificar datasets/golden regression como Module 12C. Compliance requiere política versionada antes de juzgar. Tool invocation success continúa determinístico.

## 36. Technical Debt

CONFIRMED — current terminal EvaluationRequestPort sólo propaga resumen de sesión y outcomes de tools; semántica requerirá otro contrato de evidencia.
CONFIRMED — sequence puede ser null en almacenamiento y tareas de envío de transcript son asíncronas.
CONFIRMED — public facades actuales no entregan transcript ni AgentEvaluationSnapshot.
CONFIRMED — eliminación de Agent puede borrar la versión que referencia una sesión terminal.
CONFIRMED — no hay redaction path ni proveedor/credencial LLM general confirmados.
INFERRED — el transcript durable no prueba por sí solo que el snapshot histórico exacto del agente siga resoluble tras borrado.
RECOMMENDED — cerrar esos puntos como gates de diseño, no asumirlos implícitamente en evaluator.

## 37. Acceptance Criteria

- Evidencia versionada, tenant-scoped, orden estable y estado de completitud definido.
- Exact AgentVersion usada por sesión; nunca latest; comportamiento ante versión borrada definido.
- Redaction/retención aprobadas antes de envío externo; transcript no aparece en logs.
- Tres criterios con rubric/prompt versionados, categorías explícitas y evidence IDs verificables.
- JSON tipado validado; malformed output falla cerrado.
- Provider/model/prompt/schema/implementation/latency/usage auditables; secretos fuera de modelos.
- Semantic run separado de technical-health run; semantic failure no cambia estado de Voice, Analytics, CRM o booking.
- Claim commit antes del provider call; ningún lock/DB transaction durante red; stale owner no persiste.
- Timeouts bajo lease, retries acotados, sampling/configuración documentados.
- Tests FakeLlmJudge en CI y nuevos invariants críticos con PostgreSQL; smoke de provider fuera de CI.
- DDL/OpenAPI sólo según necesidad descrita; OpenAPI esperado sin cambios.
- Architecture gates de boundaries, secretos, tenant isolation y snapshot v3/v7.

## 38. Recommended Next Action

RECOMMENDED — aprobar y ejecutar 12B.1 como discovery técnico de completitud/retención y diseño de los dos public readers; cerrar antes la política de redaction y si QA puede usar evidencia sintética. No iniciar provider adapter hasta completar qualification de proveedores y definir quién gestiona la credencial. Este reporte no implementa cambios ni crea un PR.

## Evidence Index

- Evaluations Core: backend/app/modules/evaluations/domain/technical_health.py (VoiceSessionEvidence, ToolOutcomeEvidence); backend/app/modules/evaluations/public.py (EvaluationRunner, EvaluationQueries, EvaluationFacade); backend/app/modules/evaluations/infrastructure/models.py (EvaluationDefinitionVersion, EvaluationRun, CriterionResult); backend/app/modules/evaluations/infrastructure/repositories.py (request_voice_session, claim_batch, execute, _record_failure); backend/app/modules/evaluations/runtime/worker.py (run_cycle); backend/test_evaluations_postgres.py.
- Voice transcript production: voice-runtime/src/serviglobal_voice_runtime/providers.py (on_conversation_item, emit_transcript); voice-runtime/tests/test_runtime.py (final transcript event assertions).
- Voice persistence/ingestion: backend/app/modules/voice/application/runtime_events.py (RuntimeEventIngestor.ingest); backend/app/modules/voice/application/session_service.py (VoiceSessionService.record_event, transition); backend/app/modules/voice/infrastructure/models.py (VoiceSession, VoiceSessionEvent); backend/app/modules/voice/api/router.py (_QA_EVENT_FIELDS, list_voice_session_events).
- Analytics: backend/app/modules/analytics/application/projection_service.py (voice.transcript.final ordering/projection).
- Agent snapshot: backend/app/modules/agents/infrastructure/models.py (TenantAgentVersion); backend/app/modules/agents/application/queries.py (AgentQueries.lock_published_agent, tool_bindings, describe); backend/app/modules/agents/public.py (AgentsFacade); backend/app/modules/voice/application/session_service.py (VoiceSessionService.create); backend/app/modules/voice/infrastructure/models.py (agent_version_id immutability/detachment).
- Provider/credentials: backend/app/modules/voice_providers/domain/registry.py (VoiceModel, _PROVIDERS, _MODELS); backend/app/modules/voice_providers/domain/contracts.py (ProviderCredential); backend/app/modules/voice_providers/infrastructure/credentials.py (resolve_credential); backend/requirements.txt; voice-runtime/pyproject.toml.
