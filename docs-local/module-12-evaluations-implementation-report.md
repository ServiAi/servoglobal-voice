# Module 12 — Evaluations Implementation Report

**Fecha:** 2026-10-07
**Rama:** `refactor/modular-evaluations`
**Veredicto:** **NOT READY** — falta ejecutar el gate PostgreSQL real y completar el backend suite en CI.

## Executive Summary

Se agregó el bounded context `app.modules.evaluations` con definiciones/versiones, runs tenant-scoped, resultados por criterio, una evaluación determinística de salud técnica de sesiones Voice y un worker asíncrono con claim/lease. No se agregaron endpoints ni UI. La cola durable se escribe dentro de la transacción que marca la sesión Voice terminal; el cálculo ocurre después, fuera de esa transacción.

## Branch / Commit / PR

- Rama de trabajo: `refactor/modular-evaluations`, creada desde `develop` después de confirmar `git fetch` y `git pull --ff-only origin develop` (`Already up to date`).
- Base: `37c5758`, merge de PR #128.
- Commits locales: `b546a62` (core + persistencia) y `58d5aea` (integración Voice). El commit de tests/CI/docs contiene este reporte.
- Este reporte no implica que se haya publicado una rama o abierto/actualizado un PR.

## Develop Baseline

- Alembic head previo: `202610050001` (uno).
- Metadata ORM previa: 79 tablas.
- Fingerprint DDL guardado antes de implementar: `3000fa45474ed16eeb3abf6d2bf0cf32dcc57e1d82d6d85a7bc7556b3e4782c1`.
- OpenAPI previo: 257 paths, 336 operations, 293 schemas.
- Baseline fingerprint OpenAPI: `05a1e823f21241e0cc2d9ee7a1b590a8db8a366de90e50a6265f5d45d3c1ae85`.
- El discovery document contiene la auditoría léxica y arquitectónica inicial. La confirmación remota que quedó pendiente allí se completó antes de implementar PR #129.

## Discovery Verification

La segunda búsqueda no encontró un legacy Evaluation ORM, tabla, servicio o persistencia que requiriera migración. Los eventos Voice ya guardan `tool_key`, `success/error`, duración y código de error sanitizado. No se copian transcript, argumentos ni resultados de tools.

## Ownership

Evaluations posee definiciones/versiones, ejecuciones, estado de ejecución y resultados. Voice sigue siendo dueño de sesiones y eventos; Analytics de hechos de llamadas; Scheduling/CRM de outcomes; Billing de costos. No se agregaron relaciones ORM cross-module hacia Voice, Agents, CRM, Analytics o Tenant.

## Tables Added

- `evaluation_definitions`
- `evaluation_definition_versions`
- `evaluation_runs` (incluye el resultado agregado)
- `evaluation_criterion_results`

El agregado se mantiene en `EvaluationRun` (`passed`, `score`, `reason`, `evaluated_at`); una tabla `EvaluationResult` adicional no aporta un lifecycle o invariante diferente en este alcance.

## Alembic Migration

`202610070001_evaluations_core` depende de `202610050001` y agrega una única head. Incluye constraints de ownership/tenant, identidad idempotente, unicidad de criterio y un trigger PostgreSQL para impedir cambios o borrados de versiones publicadas. Siembra la definición system-owned `voice_session_technical_health` v1.

`alembic heads` local: `202610070001 (head)`. La base local no tiene `DATABASE_URL`; `alembic current` y `upgrade head` no se pudieron demostrar localmente. CI ahora ejecuta `heads`, `upgrade head` y `current`.

## Domain Model

El dominio usa evidencia inmutable y validada (`VoiceSessionEvidence`, `ToolOutcomeEvidence`), criterios/resultados puros y errores explícitos. El run fija `agent_version_id`, versión de definición, snapshot safe y SHA-256 de evidencia. No persiste chain-of-thought, secretos, argumentos/resultados crudos o PII.

## Evaluation State Machine

Estados persistidos: `queued → running → completed|failed`; una lease expirada permite reclamar de nuevo `running`. `cancelled` no es reclamable ni puede ser completado por un worker tardío. Los intentos y backoff están acotados a cinco ejecuciones.

## Definition Versioning

La versión publicada es inmutable mediante listener ORM y trigger PostgreSQL. Cambios futuros requieren una nueva versión; cada run conserva la versión que recibió al encolarse.

## Public Boundary

`evaluations.public` expone `EvaluationRunner`, `EvaluationQueries` y `EvaluationFacade` con DTOs. Importarlo no carga SQLAlchemy ni ORM/provider de Voice, Analytics, CRM o Agents. SQLAlchemy queda en `infrastructure` y los casos de uso reciben un repositorio inyectado.

## Evidence Architecture

`VoiceSessionService` crea el request durable al entrar a un estado terminal. La evidencia se proyecta desde el DTO/estado propio de Voice y los resúmenes allowlisted `session.context.tool_used`. El adapter se compone en `voice.wiring`; no hay llamadas a proveedores ni lectura de ORM externo desde Evaluations.

## Deterministic Evaluators

La definición v1 contiene `session_terminal`, `runtime_health` y `tool_execution_health`. Es una señal de salud técnica, no de éxito de negocio. No se implementó LLM-as-a-Judge.

## Voice Trigger

Producción y QA usan la misma transición terminal. El run y el estado terminal se confirman o revierten juntos; el worker detenido no bloquea la transición ni hace evaluación inline. Un test local verifica encolado, rollback atómico y fijación de la versión histórica del agente.

## QA Integration

No cambia la UI ni el flujo WebRTC/SIP. Una sesión QA terminal usa el mismo pipeline de Voice. El resultado no se presenta en la interfaz.

## Worker / Claim / Lease

Comando: `python -m app.modules.evaluations.runtime.worker`; `--once` procesa un batch. El batch máximo es 25, lease de 60 segundos. PostgreSQL usa `FOR UPDATE SKIP LOCKED`; el claim se confirma antes del cálculo. El cierre compara token, generación y lease para bloquear owners obsoletos.

## Idempotency

La identidad incluye tenant, subject, versión de definición y `trigger_key`. El mismo hash reutiliza el run; un hash distinto registra conflicto sin reemplazar evidencia ni resultado histórico. La constraint única es la autoridad ante carreras.

## Multi-Tenant Invariants

Runs y resultados son tenant-scoped; FK compuesta impide asociar un resultado a un run de otro tenant. `owner_key` restringe una definición system o la definición del mismo tenant. Las queries requieren `tenant_id` y fallan cerradas.

## PostgreSQL Concurrency Results

La suite `test_evaluations_postgres` cubre duplicados concurrentes, conflicto de evidencia, claims concurrentes, recuperación de lease, stale worker, retry, tenant isolation, trigger de inmutabilidad, identidad de versión, cancelación tardía y atomicidad/unicidad de criterios. **No se ejecutó localmente:** falta `EVALUATIONS_TEST_DATABASE_URL`. Se agregó a CI una base dedicada `serviai_evaluations_test`; el paso falla si el test se omite.

## Architecture Gates

`test_evaluations_boundaries` verifica imports de SQLAlchemy/provider en domain/application, consumidores que acceden sólo a `evaluations.public` (con excepción explícita del registry `app.models`), ausencia de relaciones ORM cross-module y el import público sin ORM.

## DDL Comparison

Metadata posterior: 83 tablas; las cuatro tablas nuevas son de Evaluations. No se alteraron modelos/tablas existentes. Fingerprint compilado PostgreSQL posterior (tablas e índices de `Base.metadata`): `dfa31349596caa019a184ee1042db26944c890c01de2b7ca62a67c6718862c94`. La captura del fingerprint previo no conserva su rutina de serialización, así que no uso una resta de hashes como prueba de delta; la comparación de ownership confirma que los cuatro modelos añadidos pertenecen a Evaluations y no se editó ningún modelo de tabla previa. DDL real requiere `alembic upgrade head` en CI PostgreSQL.

## OpenAPI Comparison

Sin cambio: 257 paths, 336 operations, 293 schemas; fingerprint posterior idéntico al baseline: `05a1e823f21241e0cc2d9ee7a1b590a8db8a366de90e50a6265f5d45d3c1ae85`.

## Full CI Results

- Nuevos tests unitarios y architecture: **10 passed**.
- `test_module_boundaries`: **64 passed**; `test_analytics_public_orm_escape`: **5 passed**.
- Voice: `test_voice_sessions` **19 passed**, `test_voice_qa_harness` **11 passed**, `test_voice_runtime_control_plane` **44 passed** después de agregar su seed fixture.
- `python -m compileall app`: pasó con `PYTHONPYCACHEPREFIX` en una ruta temporal porque el cache local del repo tiene ACL restringida.
- Frontend: `npm.cmd run lint`, `npx.cmd tsc --noEmit --incremental false` y `npm.cmd run build` pasaron.
- `alembic heads`: un head, `202610070001`.
- El intento de correr todo el backend desde un único runner local superó el límite de ejecución de 300 s; un pase por lotes confirmó 11 módulos antes de alcanzar el límite del proceso. El backend completo no queda acreditado.
- Ruff no está instalado en el venv local. El workflow existente instala Ruff pero mantiene ese paso como `continue-on-error` por deuda preexistente.
- La suite PostgreSQL aún debe correr en CI; no se declara como prueba local.

## Technical Debt

- Ejecutar el CI PostgreSQL y corregir cualquier discrepancia entre metadata, migración y PostgreSQL real.
- Completar el backend suite y un gate Ruff bloqueante en un entorno apto.
- No se publicó el branch ni se abrió PR.

## Out of Scope

LLM judges, catálogo de outcomes, cost-per-outcome, UI/dashboard de evaluaciones, almacenamiento de transcript/argumentos/resultados crudos y refactor de Call Summary.

## Final Verdict

**NOT READY** — la implementación está lista para revisión de código, pero faltan gates de aceptación exigidos: PostgreSQL real/CI y backend suite completa.
