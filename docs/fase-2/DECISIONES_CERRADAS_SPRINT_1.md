# DECISIONES CERRADAS – SPRINT 1
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.0  
**Estado:** Decisiones cerradas previas a Sprint 1  
**Propósito:** dejar por escrito las decisiones técnicas y funcionales que quedan aprobadas antes de iniciar la implementación del Sprint 1.

---

# 1. Decisión estratégica general

## DC-001. Se mantiene el mismo repositorio
La Fase II se implementará dentro del repositorio actual `ServiAi/servoglobal-voice`.

### Implicación
- no se abrirá un repositorio separado para el dashboard;
- la evolución será incremental sobre la base existente.

---

## DC-002. No se construirá un backend distinto por negocio
La plataforma continuará evolucionando como un **backend central multitenant**.

### Implicación
- no habrá un backend independiente por cada cliente como modelo estándar;
- las diferencias entre clientes se resolverán por configuración por tenant y extensiones por excepción.

---

# 2. Decisiones sobre arquitectura

## DC-003. El backend propio será la fuente de verdad del dashboard
Todas las métricas, filtros, tendencias y tabla de llamadas recientes deberán salir del backend interno y de la base de datos propia.

### Implicación
- el frontend no leerá datos del dashboard directamente desde Ultravox;
- el dashboard consultará únicamente APIs internas del backend.

---

## DC-004. Ultravox será la fuente upstream de eventos y datos crudos
Ultravox seguirá siendo una fuente de eventos, payloads, estados y datos originales de llamadas, pero no será la fuente de lectura del dashboard.

### Implicación
- primero se ingiere;
- luego se persiste;
- luego se normaliza;
- luego se expone desde el backend propio.

---

## DC-005. Auth0 será el proveedor externo de identidad
Auth0 se usará para autenticar usuarios y gestionar sesión.

### Implicación
- Auth0 resuelve identidad;
- el backend resuelve autorización de negocio;
- tenant, memberships y roles vivirán en la base interna del producto.

---

## DC-006. La app tendrá separación clara entre superficie pública y privada
Se mantendrá la landing y los flujos públicos actuales como superficie pública, y se construirá una nueva superficie privada para el dashboard.

### Implicación
- la landing pública no debe contaminarse con lógica privada;
- el dashboard deberá vivir bajo rutas protegidas y contexto autenticado;
- no se aplicará auth global que rompa demos públicas o webhooks existentes.

---

# 3. Decisiones sobre backend

## DC-007. No habrá reescritura total del backend
El backend actual se evolucionará mediante **refactor selectivo e incremental**.

### Implicación
- no se rehace el backend desde cero;
- se agregan módulos nuevos sin tocar innecesariamente la lógica actual;
- solo se refactoriza lo necesario para soportar la Fase II.

---

## DC-008. La seguridad nueva no se mezclará completamente con la actual
La lógica de Turnstile actual no debe convertirse en la base de auth del dashboard.

### Implicación
- no se usará `api/deps.py` como contenedor único de toda la seguridad nueva;
- se crearán dependencias nuevas y separadas para:
  - autenticación,
  - tenant,
  - rol,
  - permisos.

---

## DC-009. La lógica analítica no se mezclará con la lógica de demos
Los servicios actuales orientados a demo o outbound no deben transformarse en el núcleo del dashboard analítico.

### Implicación
- `voice_service.py` deberá mantenerse lo más estable posible;
- la persistencia, normalización y analítica deberán vivir en servicios nuevos.

---

# 4. Decisiones sobre modelo de datos

## DC-010. En Sprint 1 se implementará primero el modelo de identidad y tenant
Antes de tocar el dashboard visual se construirá la base de autenticación y autorización del producto.

### Entidades mínimas aprobadas para Sprint 1
- `users`
- `tenants`
- `tenant_memberships`
- `access_audit_logs`

### Implicación
- el modelo completo de llamadas y métricas queda para el siguiente sprint;
- Sprint 1 no entra todavía a `calls`, `call_events` ni `metric_snapshots_daily`.

---

## DC-011. Se introducirá base de datos propia y migraciones
La Fase II no continuará sin persistencia formal del backend.

### Implicación
- se agregará capa de base de datos;
- se agregará ORM o equivalente coherente con el backend actual;
- se agregarán migraciones;
- el sistema deberá quedar listo para crecer sin hacks temporales.

---

# 5. Decisiones sobre autorización

## DC-012. El backend resolverá `current_user`, `current_tenant` y `current_role`
Toda autorización relevante del dashboard se resolverá desde backend.

### Implicación
- el frontend puede ocultar o mostrar UI;
- pero la validación final siempre será backend;
- el tenant no se confiará a parámetros arbitrarios enviados por el cliente.

---

## DC-013. Se expondrá `/api/v1/me` en Sprint 1
Este endpoint será la base de la app privada y del contexto del usuario autenticado.

### Implicación
- el frontend privado podrá resolver:
  - usuario actual,
  - tenant actual,
  - rol actual,
  - tipo de usuario;
- el dashboard visual completo todavía no será implementado en Sprint 1.

---

# 6. Decisiones sobre frontend

## DC-014. Sprint 1 no implementará el dashboard visual completo
El frontend analítico no se construirá todavía.

### Implicación
- no habrá KPI cards;
- no habrá charts;
- no habrá heatmap;
- no habrá tabla de llamadas recientes visual en Sprint 1.

---

## DC-015. Solo se preparará la base privada mínima del frontend
En Sprint 1, el frontend solo deberá quedar listo para convivir con autenticación y futuras rutas privadas.

### Implicación
- guardas mínimas;
- resolución de sesión/perfil;
- preparación de rutas privadas;
- sin entrar aún a componentes analíticos complejos.

---

# 7. Alcance aprobado de Sprint 1

## DC-016. Sprint 1 queda oficialmente limitado a:

### Backend
- integración base con Auth0;
- incorporación de base de datos y migraciones iniciales;
- creación de:
  - `users`
  - `tenants`
  - `tenant_memberships`
  - `access_audit_logs`
- dependencias reutilizables:
  - `current_user`
  - `current_tenant`
  - `current_role`
- endpoint `GET /api/v1/me`

### Frontend
- base mínima para sesión/rutas privadas;
- sin dashboard visual completo.

### No aprobado para Sprint 1
- `agents`
- `calls`
- `call_events`
- `metric_snapshots_daily`
- ingestión desde Ultravox
- normalización de estados
- endpoints de métricas
- KPI cards
- heatmap
- recent calls UI

---

# 8. Restricciones aprobadas para Codex en Sprint 1

## DC-017. Codex no debe:
- romper la landing pública actual;
- romper los endpoints públicos actuales;
- aplicar auth global a demos públicas o webhooks;
- hacer refactors masivos no solicitados;
- rediseñar toda la arquitectura del repo;
- construir el dashboard visual completo;
- usar Ultravox como fuente de lectura del dashboard.

---

# 9. Criterio de salida de Sprint 1

## DC-018. Sprint 1 se considerará terminado cuando:
- exista integración funcional de identidad con Auth0;
- el backend pueda resolver usuario interno;
- el backend pueda resolver tenant y rol;
- exista membresía activa por tenant;
- usuarios sin membresía queden bloqueados;
- exista `GET /api/v1/me`;
- la base del producto quede lista para entrar a modelo de datos analítico en Sprint 2;
- la funcionalidad pública actual siga operando.

---

# 10. Próximo paso autorizado

## DC-019. El siguiente paso autorizado es preparar el prompt de implementación de Sprint 1
Una vez aprobado este documento, el siguiente paso será entregar a Codex un prompt limitado exclusivamente al alcance de Sprint 1.
