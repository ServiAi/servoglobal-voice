# Implementation Plan
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.0  
**Estado:** Plan operativo de implementación  
**Objetivo:** ejecutar la Fase II como evolución controlada del repositorio actual hacia una plataforma central multitenant, sin romper el servicio funcional existente.

---

# 1. Objetivo de la Fase II

Construir un dashboard multicliente de métricas para clientes que permita consultar:

- llamadas totales;
- llamadas contestadas y no contestadas;
- tasa de contestación;
- duración promedio y total;
- minutos facturados;
- distribución por agente;
- actividad por día y hora;
- tabla de llamadas recientes;
- resúmenes de llamada.

La arquitectura deberá asegurar que:

- el **backend propio** sea la fuente de verdad del dashboard;
- **Ultravox** sea la fuente upstream de eventos y datos crudos;
- **Auth0** resuelva identidad;
- la plataforma opere como **backend central multitenant**;
- la personalización se haga por **configuración por tenant** y no por un backend distinto por negocio.

---

# 2. Decisiones de arquitectura

## 2.1 Plataforma
La Fase II se implementará sobre un **core backend compartido** para todos los clientes.

## 2.2 Fuente de verdad
El dashboard leerá únicamente desde la **base de datos interna** de la plataforma.

## 2.3 Proveedor de identidad
La autenticación se implementará con **Auth0**.

## 2.4 Fuente upstream
Ultravox proveerá eventos y datos crudos de llamadas para ingestión, sincronización y reconciliación.

## 2.5 Personalización
Las diferencias entre clientes se resolverán mediante:
- configuración por tenant;
- agentes por tenant;
- reglas por tenant;
- integraciones configurables;
- extensiones por excepción.

## 2.6 Regla de implementación
La Fase II se construirá en orden:
1. documentación;
2. autenticación, tenant y roles;
3. modelo de datos;
4. ingesta y normalización;
5. API interna del dashboard;
6. frontend del dashboard;
7. QA y hardening.

---

# 3. Alcance

## Incluye
- documentación de Fase II dentro del repositorio;
- integración con Auth0;
- modelo de usuarios, tenants, memberships y roles;
- modelo de llamadas, eventos y snapshots;
- persistencia interna de llamadas;
- normalización de estados;
- endpoints privados del dashboard;
- frontend del dashboard;
- filtros, KPIs, gráficos y tabla de llamadas;
- auditoría de accesos;
- pruebas y documentación técnica.

## Excluye
- reescritura completa del backend actual;
- dashboard leyendo directo desde Ultravox;
- un backend distinto por cada negocio como patrón principal;
- exportación avanzada de reportes;
- facturación automática;
- administración avanzada de usuarios finales;
- módulos financieros;
- analítica conversacional avanzada;
- alertas inteligentes por KPI.

---

# 4. No alcance

No forman parte de esta fase:

- SSO corporativo avanzado;
- federación empresarial;
- branded login por cliente;
- MFA obligatorio;
- administración visual completa de organizaciones;
- scoring avanzado;
- sentiment analysis;
- rediseño completo del producto comercial o landing pública;
- despliegues aislados por cliente como estrategia base.

---

# 5. Orden de implementación recomendado

La implementación deberá seguir este orden estricto:

## 5.1 Sprint 0
- documentación consolidada;
- alcance congelado;
- checklist de salida;
- prompt de diagnóstico para Codex.

## 5.2 Sprint 1
- Auth0;
- users;
- tenants;
- tenant_memberships;
- access_audit_logs;
- `/api/v1/me`;
- seguridad base del dashboard.

## 5.3 Sprint 2
- agents;
- calls;
- call_events;
- metric_snapshots_daily;
- migraciones;
- índices;
- relaciones.

## 5.4 Sprint 3
- ingesta desde Ultravox;
- persistencia de eventos;
- normalización de estados;
- reconciliación/backfill inicial;
- asociación de llamadas a tenant y agente.

## 5.5 Sprint 4
- endpoints internos del dashboard;
- KPIs;
- trends;
- distributions;
- heatmap;
- recent calls.

## 5.6 Sprint 5
- frontend del dashboard;
- layout privado;
- filtros;
- KPI cards;
- charts;
- tabla reciente;
- estados vacíos y errores.

## 5.7 Sprint 6
- pruebas;
- fixtures;
- documentación técnica;
- validación de tenant isolation;
- polish;
- pendientes Fase III.

---

# 6. Plan por sprints

## Sprint 0 — Preparación y alineación
### Objetivo
Dejar documentación, estructura y alcance listos para iniciar construcción.

### Entregables
- `docs/fase-2/REGLAS_NEGOCIO_FASE_II_DASHBOARD.md`
- `docs/fase-2/SPECS_FASE_II_DASHBOARD_COMPLETAS.md`
- `docs/fase-2/HISTORIAS_USUARIO_FASE_II_DASHBOARD.md`
- `docs/fase-2/IMPLEMENTATION_PLAN_FASE_II.md`
- `docs/fase-2/SPRINT_0_CHECKLIST.md`

### Criterio de cierre
- documentos versionados;
- alcance congelado;
- prompt de diagnóstico listo.

---

## Sprint 1 — Fundaciones de identidad y multitenancy
### Objetivo
Crear la base de autenticación, tenant y autorización.

### Entregables
- Auth0 integrado;
- users;
- tenants;
- memberships;
- roles;
- `/api/v1/me`;
- guardas y dependencias de seguridad.

### Criterio de cierre
- usuario autenticado resuelto;
- usuario sin membership bloqueado;
- tenant resuelto desde backend.

---

## Sprint 2 — Modelo de datos del dashboard
### Objetivo
Crear la estructura persistente que soportará el dashboard.

### Entregables
- `agents`
- `calls`
- `call_events`
- `metric_snapshots_daily`
- migraciones
- índices

### Criterio de cierre
- llamadas persistibles;
- relaciones tenant/agent/call válidas;
- migraciones aplicables sin romper el repo actual.

---

## Sprint 3 — Ingesta y normalización
### Objetivo
Persistir y normalizar internamente llamadas provenientes de Ultravox.

### Entregables
- servicio de ingestión;
- normalización de estados;
- reconciliación inicial;
- `last_synced_at`.

### Criterio de cierre
- el backend ya almacena llamadas internas utilizables por el dashboard.

---

## Sprint 4 — API interna del dashboard
### Objetivo
Exponer la capa de datos analíticos que consumirá el frontend.

### Endpoints
- `GET /api/v1/dashboard/kpis`
- `GET /api/v1/dashboard/trends`
- `GET /api/v1/dashboard/status-distribution`
- `GET /api/v1/dashboard/agent-distribution`
- `GET /api/v1/dashboard/heatmap`
- `GET /api/v1/dashboard/recent-calls`

### Criterio de cierre
- endpoints protegidos;
- filtros funcionando;
- tenant isolation garantizado;
- consistencia entre KPIs y tabla.

---

## Sprint 5 — Frontend del dashboard
### Objetivo
Construir la primera versión usable del dashboard.

### Entregables
- ruta privada;
- layout;
- filtros;
- cards KPI;
- charts;
- tabla de llamadas;
- empty states;
- retry/error states.

### Criterio de cierre
- dashboard usable por usuarios autenticados del tenant correcto.

---

## Sprint 6 — QA, hardening y documentación técnica
### Objetivo
Estabilizar la fase para validación interna y futura evolución.

### Entregables
- pruebas unitarias;
- pruebas de integración;
- fixtures;
- documentación técnica;
- checklist de validación;
- lista de pendientes Fase III.

### Criterio de cierre
- pruebas ejecutables;
- dashboard estable;
- riesgos conocidos documentados.

---

# 7. Plan por PRs

## PR-00
Documentación de Fase II dentro del repo

## PR-01
Auth0 base frontend/backend

## PR-02
Users + tenants + memberships + `/api/v1/me`

## PR-03
Modelo de datos: `agents`, `calls`, `call_events`

## PR-04
Snapshots + audit logs + migraciones finales del modelo

## PR-05
Ingesta base de llamadas desde Ultravox

## PR-06
Normalización de estados + reconciliación inicial

## PR-07
Dashboard API: KPIs + trends

## PR-08
Dashboard API: distributions + heatmap + recent calls

## PR-09
Frontend dashboard shell + auth guards

## PR-10
KPI cards + charts

## PR-11
Recent calls table + filtros + empty states

## PR-12
Tests + fixtures + docs

## PR-13
Polish + fixes finales

---

# 8. Riesgos

## Riesgo 1. Romper el servicio actual
**Mitigación:** cambios incrementales, PRs pequeños, refactor selectivo, no reescritura total.

## Riesgo 2. Acoplar el dashboard a Ultravox
**Mitigación:** persistencia interna obligatoria y backend como fuente de verdad.

## Riesgo 3. Ambigüedad entre tenant, usuario y permisos
**Mitigación:** Auth0 solo para identidad; roles, memberships y tenant resueltos en backend.

## Riesgo 4. Personalización excesiva por cliente
**Mitigación:** configuración por tenant y extensiones por excepción, no forks del backend.

## Riesgo 5. Inconsistencia entre KPIs y tabla reciente
**Mitigación:** una sola lógica de filtros y una sola fuente de datos en backend.

## Riesgo 6. Alto costo de consulta histórica
**Mitigación:** índices, snapshots diarios y diseño preparado para optimización.

## Riesgo 7. Eventos perdidos o tardíos desde Ultravox
**Mitigación:** reconciliación, backfill y campo `last_synced_at`.

---

# 9. Dependencias

## Dependencias de negocio
- reglas de negocio actualizadas;
- SPECS completas actualizadas;
- historias de usuario actualizadas.

## Dependencias técnicas
- proveedor Auth0 configurado;
- base de datos lista para migraciones;
- estructura del backend actual conocida;
- contratos de API del dashboard definidos;
- mecanismo de ingestión desde Ultravox disponible o stub preparado.

## Dependencias operativas
- rama de trabajo para Fase II;
- checklist de Sprint 0;
- prompts preparados para Codex;
- revisión humana por PR.

---

# 10. Criterios de salida de Sprint 0

Sprint 0 se considera completo cuando:

- existe `docs/fase-2/`;
- existen reglas de negocio, SPECS e historias de usuario;
- existe este implementation plan;
- existe un checklist de Sprint 0;
- el alcance de Fase II está congelado;
- la rama de trabajo está creada;
- la documentación fue commiteada;
- existe un prompt listo para diagnóstico técnico del repo con Codex.

---

# 11. Reglas de ejecución con Codex

Cada tarea deberá ejecutarse con estas reglas:

- una tarea por prompt;
- usar siempre la documentación de `docs/fase-2/` como contrato;
- no romper la funcionalidad actual;
- no hacer refactors masivos no solicitados;
- priorizar cambios pequeños, revisables y compatibles con el repo existente;
- agregar pruebas cuando aplique;
- devolver siempre:
  - resumen,
  - archivos modificados,
  - migraciones,
  - comandos ejecutados,
  - pruebas ejecutadas,
  - riesgos y pendientes detectados.

---

# 12. Definición de éxito de la Fase II

La Fase II se considerará exitosa cuando:

- exista un dashboard privado funcional por tenant;
- la autenticación esté resuelta con Auth0;
- los datos del dashboard provengan del backend interno;
- Ultravox solo actúe como fuente upstream;
- el tenant isolation esté garantizado;
- la personalización por cliente pueda resolverse mediante configuración por tenant;
- el producto quede listo para crecer como plataforma central multitenant.

---

# 13. Próximo paso después del Sprint 0

Una vez cerrado el Sprint 0, el siguiente paso será iniciar:

## Sprint 1
- Auth0
- users
- tenants
- tenant_memberships
- access_audit_logs
- `/api/v1/me`
- seguridad base del dashboard
