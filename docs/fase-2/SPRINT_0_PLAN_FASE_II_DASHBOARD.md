# Sprint 0 Plan
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.0  
**Estado:** Plan operativo inicial  
**Objetivo del Sprint 0:** alinear, congelar y dejar lista toda la documentación base para iniciar la construcción de la Fase II sin ambigüedades.

---

# 1. Objetivo del Sprint 0

El Sprint 0 **no es un sprint de desarrollo funcional**.  
Su objetivo es dejar el proyecto listo para entrar en construcción controlada, con:

- documentación consolidada dentro del repositorio;
- estructura de archivos definida;
- alcance congelado;
- secuencia de implementación documentada;
- checklist de salida;
- prompt de diagnóstico listo para usar con Codex.

---

# 2. Resultado esperado al finalizar el Sprint 0

Al terminar este sprint, el repositorio deberá tener:

```text
docs/
  fase-2/
    REGLAS_NEGOCIO_FASE_II_DASHBOARD.md
    SPECS_FASE_II_DASHBOARD_COMPLETAS.md
    HISTORIAS_USUARIO_FASE_II_DASHBOARD.md
    IMPLEMENTATION_PLAN_FASE_II.md
    SPRINT_0_CHECKLIST.md
```

Y además:

- una rama de trabajo para Fase II;
- documentación revisada y congelada;
- un commit exclusivamente documental;
- el prompt de diagnóstico preparado para Codex.

---

# 3. Alcance del Sprint 0

## Incluye
- creación de rama de trabajo;
- creación de carpeta `docs/fase-2/`;
- incorporación de documentación base;
- organización de archivos;
- definición del plan de implementación;
- creación del checklist de salida;
- preparación del prompt inicial para Codex.

## No incluye
- integración con Auth0;
- cambios en backend;
- cambios en frontend;
- migraciones;
- endpoints;
- dashboard visual;
- refactor técnico del repositorio;
- pruebas funcionales del módulo.

---

# 4. Pasos del Sprint 0

## Paso 1. Crear rama de trabajo

Ejecutar:

```bash
git checkout develop
git pull
git checkout -b feature/fase-2-dashboard-metricas
```

### Resultado esperado
- la Fase II se trabaja en una rama aislada;
- no se mezclan cambios documentales con la rama principal.

---

## Paso 2. Crear estructura documental

Crear dentro del repositorio:

```text
docs/fase-2/
```

### Resultado esperado
- existe una ubicación única y estable para toda la documentación de Fase II.

---

## Paso 3. Incorporar reglas de negocio

Crear o copiar el archivo:

```text
docs/fase-2/REGLAS_NEGOCIO_FASE_II_DASHBOARD.md
```

### Debe contener
- reglas de negocio actualizadas;
- backend multitenant como plataforma central;
- backend propio como fuente de verdad;
- Auth0 para identidad;
- Ultravox como fuente upstream;
- configuración por tenant;
- roles, memberships y tenant isolation.

### Resultado esperado
- las decisiones de negocio y arquitectura funcional quedan formalizadas.

---

## Paso 4. Incorporar SPECS completas

Crear o copiar el archivo:

```text
docs/fase-2/SPECS_FASE_II_DASHBOARD_COMPLETAS.md
```

### Debe contener
- arquitectura completa;
- capas del sistema;
- orden de implementación;
- modelo de datos;
- endpoints del dashboard;
- flujos de autenticación;
- tenant resolution;
- integración con Ultravox;
- estrategia multitenant.

### Resultado esperado
- existe un contrato técnico y funcional claro para construir la fase.

---

## Paso 5. Incorporar historias de usuario

Crear o copiar el archivo:

```text
docs/fase-2/HISTORIAS_USUARIO_FASE_II_DASHBOARD.md
```

### Debe contener
- historias de dashboard;
- historias de autenticación;
- historias de multitenancy;
- historias de configuración por tenant;
- historias de ingestión y normalización;
- historias de autorización y auditoría.

### Resultado esperado
- existe backlog funcional claro y alineado con las SPECS.

---

## Paso 6. Crear el plan de implementación

Crear el archivo:

```text
docs/fase-2/IMPLEMENTATION_PLAN_FASE_II.md
```

### Estructura recomendada
1. Objetivo de la Fase II  
2. Decisiones de arquitectura  
3. Alcance  
4. No alcance  
5. Orden de implementación  
6. Plan por sprints  
7. Plan por PRs  
8. Riesgos  
9. Dependencias  
10. Criterios de salida de Sprint 0  

### Resultado esperado
- existe una guía operativa clara para construir la fase por etapas.

---

## Paso 7. Crear checklist de salida

Crear el archivo:

```text
docs/fase-2/SPRINT_0_CHECKLIST.md
```

### Contenido recomendado
```markdown
# Sprint 0 Checklist

## Documentación base
- [ ] Existe `docs/fase-2/`
- [ ] Existe `REGLAS_NEGOCIO_FASE_II_DASHBOARD.md`
- [ ] Existe `SPECS_FASE_II_DASHBOARD_COMPLETAS.md`
- [ ] Existe `HISTORIAS_USUARIO_FASE_II_DASHBOARD.md`
- [ ] Existe `IMPLEMENTATION_PLAN_FASE_II.md`

## Alineación funcional
- [ ] Backend como fuente de verdad definido
- [ ] Ultravox como fuente upstream definido
- [ ] Plataforma multitenant definida
- [ ] Auth0 definido como proveedor de identidad
- [ ] Configuración por tenant definida
- [ ] Orden backend → API → frontend definido

## Alineación técnica
- [ ] Modelo de datos incluido en SPECS
- [ ] Roles y tenant incluidos
- [ ] Endpoints del dashboard definidos
- [ ] Orden de implementación documentado
- [ ] Riesgos documentados

## Listo para Sprint 1
- [ ] Alcance congelado
- [ ] Prompt de diagnóstico para Codex preparado
- [ ] Rama de trabajo creada
- [ ] Cambios documentales listos para commit
```

### Resultado esperado
- existe una forma clara de validar si el Sprint 0 realmente terminó.

---

## Paso 8. Congelar alcance

Durante Sprint 0 se deberá aplicar esta regla:

- si algo ya está decidido y documentado, se congela;
- si aparece una nueva idea no crítica, se envía a backlog futuro;
- no se amplía el alcance de Fase II mientras se prepara la base documental.

### Resultado esperado
- Codex y el equipo trabajarán con un contrato estable y no con un blanco móvil.

---

## Paso 9. Hacer commit documental

Cuando toda la documentación esté dentro del repo, ejecutar:

```bash
git add docs/fase-2/
git commit -m "docs: add sprint 0 documentation for phase 2 dashboard"
```

### Resultado esperado
- el estado documental del Sprint 0 queda versionado y trazable.

---

## Paso 10. Preparar prompt de diagnóstico para Codex

Usar el siguiente prompt como primera interacción técnica con Codex:

```text
Trabaja sobre este repositorio.

Lee primero estos archivos:
- docs/fase-2/REGLAS_NEGOCIO_FASE_II_DASHBOARD.md
- docs/fase-2/SPECS_FASE_II_DASHBOARD_COMPLETAS.md
- docs/fase-2/HISTORIAS_USUARIO_FASE_II_DASHBOARD.md
- docs/fase-2/IMPLEMENTATION_PLAN_FASE_II.md

OBJETIVO
No implementes todavía.
Quiero que inspecciones el repositorio actual y me entregues un diagnóstico técnico para iniciar la Fase II.

Necesito que me digas:
1. cómo está organizada la arquitectura actual;
2. dónde encajan Auth0, tenant, roles y dashboard;
3. qué partes del backend necesitan refactor selectivo;
4. qué archivos o módulos probablemente habrá que crear o modificar;
5. cuál es el orden más seguro de implementación;
6. qué riesgos ves para no romper el servicio existente.

RESTRICCIONES
- No cambies código todavía.
- No hagas refactors todavía.
- No propongas rehacer todo el repo desde cero.
- Prioriza cambios incrementales y compatibles con el servicio actual.

ENTREGABLE
- diagnóstico del repo;
- plan por etapas;
- lista de archivos a tocar;
- riesgos;
- dependencias técnicas;
- secuencia recomendada de implementación.
```

### Resultado esperado
- el proyecto queda listo para entrar a Sprint 1 con diagnóstico real del repositorio.

---

# 5. Definición de terminado del Sprint 0

El Sprint 0 se considera completo cuando:

- existe la rama `feature/fase-2-dashboard-metricas`;
- existe `docs/fase-2/`;
- existen las reglas de negocio;
- existen las SPECS completas;
- existen las historias de usuario;
- existe el implementation plan;
- existe el checklist;
- el alcance está congelado;
- la documentación fue commiteada;
- el prompt de diagnóstico está listo para Codex.

---

# 6. Riesgos del Sprint 0

## Riesgo 1. Documentación inconsistente
**Mitigación:** revisar que reglas, SPECS e historias cuenten la misma arquitectura.

## Riesgo 2. Alcance inestable
**Mitigación:** congelar decisiones y enviar nuevas ideas a backlog futuro.

## Riesgo 3. Empezar a programar demasiado pronto
**Mitigación:** no tocar código hasta terminar la salida de Sprint 0.

## Riesgo 4. Darle a Codex documentación incompleta
**Mitigación:** validar que todos los documentos estén dentro del repo antes del diagnóstico.

---

# 7. Salida del Sprint 0

La salida oficial de Sprint 0 debe ser:

- documentación base lista dentro del repositorio;
- rama de trabajo creada;
- commit documental realizado;
- checklist completado;
- prompt de diagnóstico preparado.

Una vez completado eso, el proyecto queda listo para iniciar:

## Sprint 1
- Auth0
- users
- tenants
- memberships
- roles
- `/api/v1/me`
- seguridad base del dashboard
