# SPECS completas actualizadas
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.3  
**Estado:** Draft funcional-técnico consolidado  
**Módulo:** Dashboard multicliente de métricas, autenticación, roles, tenant y arquitectura de plataforma  
**Decisiones tecnológicas clave:**  
- Auth0 como proveedor externo de identidad  
- FastAPI como backend y fuente de verdad operativa/analítica  
- Next.js como frontend del dashboard  
- Ultravox como fuente upstream de eventos y datos crudos  
- Plataforma central multitenant con configuración por tenant y extensiones por excepción

---

# 1. Resumen ejecutivo

La Fase II tiene como objetivo construir un **dashboard de métricas multicliente** que permita a cada cliente autenticado ingresar a la plataforma y consultar el desempeño operativo de sus agentes de voz y de sus llamadas.

El dashboard deberá mostrar métricas agregadas, gráficos operativos y una tabla de llamadas recientes, todo filtrado por cliente y calculado desde la **base de datos interna del sistema**.

La arquitectura base definida para esta fase establece que:

- **Ultravox** será la fuente upstream de eventos y datos crudos.
- **El backend propio** será la fuente de verdad operativa y analítica.
- **Auth0** será el proveedor externo de identidad.
- **El frontend** consumirá únicamente APIs internas del backend.
- **La plataforma** se construirá como un backend central multitenant y no como un backend distinto por cada negocio.

---

# 2. Objetivo del módulo

Construir un dashboard que permita a cada cliente:

- ver llamadas totales;
- ver llamadas contestadas y no contestadas;
- consultar duración promedio y total;
- visualizar actividad por agente;
- analizar el comportamiento por día y hora;
- revisar una tabla de llamadas recientes;
- revisar resúmenes de llamadas;
- monitorear el estado general de la operación.

---

# 3. Objetivos funcionales y técnicos

## 3.1 Objetivos funcionales

- Proveer una vista consolidada del comportamiento de llamadas por cliente.
- Permitir análisis por rango de fechas, agente y estado.
- Presentar información útil para operación, supervisión y toma de decisiones.
- Diseñar una base extensible para futuras fases de reportes, exportaciones, scoring y analítica avanzada.
- Permitir crecimiento del producto sin duplicar backend por cliente.

## 3.2 Objetivos técnicos

- Desacoplar el dashboard del proveedor externo.
- Centralizar en el backend interno la lógica de métricas.
- Persistir llamadas y eventos en base de datos.
- Soportar multicliente desde el diseño.
- Permitir sincronización incremental y reconciliación con Ultravox.
- Resolver autenticación con proveedor externo y autorización de negocio en backend.
- Soportar configuración por tenant sin bifurcar el core del producto.

---

# 4. No objetivos de esta fase

Esta fase **no incluye**:

- edición manual de llamadas;
- eliminación de llamadas;
- facturación automática;
- exportación avanzada a PDF/Excel;
- alertas automáticas por KPI;
- monitoreo full real-time con websockets obligatorios;
- administración avanzada de campañas;
- módulo financiero;
- gestión visual completa de usuarios y organizaciones;
- análisis de sentimiento o scoring conversacional avanzado;
- SSO corporativo avanzado;
- federación empresarial;
- branded login por cliente;
- MFA obligatorio;
- delegación granular por módulo;
- backends independientes por cada negocio como modelo estándar.

---

# 5. Alcance funcional

## 5.1 Incluye

- autenticación y acceso al dashboard;
- aislamiento de información por cliente;
- KPIs principales;
- filtros por fecha, estado y agente;
- visualizaciones agregadas;
- tabla de llamadas recientes;
- resúmenes de llamadas;
- normalización de estados;
- lectura desde base interna;
- integración backend con eventos de Ultravox;
- reconciliación/sincronización de datos;
- resolución de tenant, membresías y roles;
- configuración por tenant como base de personalización.

## 5.2 Excluye

- consumo directo de la API de Ultravox desde frontend;
- gestión de seguridad avanzada fuera del alcance del dashboard;
- edición de resúmenes;
- etiquetado manual de llamadas;
- dashboards comparativos multiempresa visibles al cliente;
- una implementación completamente distinta del backend por cada cliente como patrón principal.

---

# 6. Actores del sistema

## 6.1 Administrador interno de plataforma
Puede consultar métricas de cualquier cliente para soporte, operación y auditoría.

## 6.2 Administrador cliente
Puede consultar todas las métricas de su empresa y navegar toda la información analítica del tenant.

## 6.3 Analista / visualizador cliente
Puede consultar métricas y llamadas, pero no administrar la configuración del tenant.

---

# 7. Decisiones de arquitectura

## 7.1 Estrategia de plataforma
La plataforma se construirá como un **backend central multitenant** que soporte múltiples clientes bajo un mismo core compartido.

## 7.2 Configuración por tenant
La personalización por negocio deberá resolverse principalmente mediante:
- configuración por tenant;
- agentes por tenant;
- prompts;
- workflows;
- reglas de routing;
- handoff;
- integraciones configurables.

## 7.3 Extensiones por excepción
Solo en casos de regulación, infraestructura dedicada o lógica extremadamente especializada se permitirán extensiones especiales o despliegues aislados.

## 7.4 Fuente de verdad
La fuente oficial de verdad del dashboard será la **base de datos interna** del sistema.

## 7.5 Fuente externa
Ultravox será usado como fuente de:
- eventos de llamadas;
- datos crudos;
- resúmenes;
- duraciones;
- metadata de llamada;
- reconciliación y backfill.

## 7.6 Proveedor de identidad
La plataforma usará **Auth0** como proveedor externo de identidad.

## 7.7 Separación de responsabilidades

### Auth0 será responsable de:
- autenticación;
- login;
- logout;
- sesión del usuario;
- identidad externa del usuario;
- recuperación de acceso;
- emisión de tokens.

### El backend propio será responsable de:
- resolver usuario interno;
- resolver tenant activo;
- resolver rol interno;
- aplicar autorización funcional;
- aislar datos por cliente;
- proteger endpoints del dashboard;
- auditar accesos;
- calcular y exponer métricas;
- soportar configuración por tenant.

## 7.8 Flujo general de datos
```text
Ultravox → Webhooks / Sync Jobs → Backend propio → Base de datos interna → API interna → Frontend dashboard
```

## 7.9 Regla central
La autenticación se resuelve fuera del sistema, pero la autorización de negocio y la lógica analítica se resuelven dentro del backend propio.

---

# 8. Capas de la arquitectura objetivo

## 8.1 Frontend layer
Aplicación web en Next.js compuesta por:
- landing pública;
- app privada;
- dashboard de métricas.

## 8.2 Auth / Identity layer
Auth0 como proveedor externo de identidad.

## 8.3 Core backend layer
FastAPI como backend compartido con:
- usuarios internos;
- tenants;
- memberships;
- roles;
- llamadas;
- métricas;
- auditoría;
- APIs privadas.

## 8.4 Tenant configuration layer
Capa de configuración por tenant para:
- prompts;
- workflows;
- routing;
- calendarios;
- CRM;
- reglas del negocio;
- webhooks y adaptadores.

## 8.5 Integration layer
Integraciones externas como:
- Ultravox;
- PBX/Asterisk;
- WhatsApp;
- CRM;
- Email;
- calendarios;
- webhooks.

## 8.6 Analytics layer
Módulo analítico del backend encargado de:
- KPIs;
- tendencias;
- heatmap;
- tabla de llamadas recientes;
- distribuciones por agente y estado.

## 8.7 Data layer
Base de datos interna como fuente oficial del dashboard.

---

# 9. Requerimientos funcionales del dashboard

## 9.1 Acceso al dashboard

### RF-001
El sistema deberá permitir que un usuario autenticado acceda al dashboard según su rol y tenant.

### RF-002
El sistema deberá bloquear el acceso a cualquier información de otro tenant.

### RF-003
El sistema deberá redirigir o rechazar el acceso si el usuario no está autenticado o no tiene permisos.

## 9.2 Vista principal del dashboard

### RF-004
La vista principal deberá mostrar KPIs resumidos del periodo filtrado.

### RF-005
La vista principal deberá incluir, como mínimo, los siguientes KPIs:
- llamadas totales;
- llamadas contestadas;
- llamadas no contestadas;
- tasa de contestación;
- duración promedio;
- duración total;
- minutos facturados, si aplica;
- llamadas en curso.

### RF-006
Todos los KPIs deberán cambiar al aplicar filtros.

## 9.3 Tabla de llamadas recientes

### RF-007
El dashboard deberá incluir una tabla de llamadas recientes.

### RF-008
La tabla deberá mostrar como mínimo:
- fecha;
- hora;
- duración;
- agente;
- resumen;
- estado.

### RF-009
La tabla deberá permitir paginación o carga incremental.

### RF-010
La tabla deberá ordenarse por fecha/hora descendente por defecto.

### RF-011
La tabla deberá reflejar exactamente los filtros activos.

## 9.4 Filtros

### RF-012
El dashboard deberá permitir filtrar por rango de fechas.

### RF-013
El dashboard deberá ofrecer filtros rápidos:
- hoy;
- últimos 7 días;
- últimos 30 días;
- este mes;
- rango personalizado.

### RF-014
El dashboard deberá permitir filtrar por agente.

### RF-015
El dashboard deberá permitir filtrar por estado.

### RF-016
Todos los componentes del dashboard deberán responder de forma consistente a los filtros aplicados.

## 9.5 Visualizaciones y gráficos

### RF-017
El dashboard deberá mostrar una tendencia de llamadas en el tiempo.

### RF-018
El dashboard deberá mostrar distribución de llamadas por estado.

### RF-019
El dashboard deberá mostrar distribución de llamadas por agente.

### RF-020
El dashboard deberá mostrar volumen de llamadas por día y hora, preferiblemente con heatmap o visual equivalente.

### RF-021
El dashboard deberá estar preparado para mostrar comparativos contra periodo anterior.

## 9.6 Métricas y definiciones

### RF-022
La métrica `llamadas totales` deberá incluir todas las llamadas del periodo.

### RF-023
La métrica `llamadas contestadas` deberá incluir solo llamadas con conexión efectiva según lógica interna.

### RF-024
La métrica `llamadas no contestadas` deberá incluir llamadas que no lograron conexión efectiva.

### RF-025
La `tasa de contestación` se calculará así:

```text
llamadas contestadas / llamadas totales elegibles * 100
```

### RF-026
La duración promedio se calculará únicamente sobre llamadas contestadas.

### RF-027
Los minutos facturados deberán provenir del dato sincronizado y persistido por el backend.

## 9.7 Asociación por agente

### RF-028
Cada llamada deberá asociarse a un agente cuando sea posible.

### RF-029
Si no existe asociación válida, se usará la categoría `Sin agente asignado`.

### RF-030
Las métricas por agente deberán incluir una categoría controlada para llamadas no asignadas.

## 9.8 Resúmenes de llamada

### RF-031
El sistema deberá mostrar resumen de llamada cuando exista.

### RF-032
Si no existe resumen, se deberá mostrar un estado controlado como:
- `Sin resumen`
- `Resumen no disponible`

### RF-033
La ausencia de resumen no deberá excluir la llamada del dashboard.

## 9.9 Actualización de datos

### RF-034
El dashboard no requiere tiempo real estricto, pero sí actualización razonable.

### RF-035
Las llamadas en curso podrán refrescarse de forma periódica.

### RF-036
El sistema deberá soportar reconciliación para completar datos faltantes.

---

# 10. Métricas incluidas en Fase II

## 10.1 KPIs principales
- llamadas totales;
- llamadas contestadas;
- llamadas no contestadas;
- tasa de contestación;
- duración promedio;
- duración total;
- minutos facturados;
- llamadas en curso.

## 10.2 Métricas analíticas sugeridas
- porcentaje de llamadas por estado;
- top agentes por llamadas;
- top agentes por duración;
- horas pico;
- tendencia diaria;
- tendencia por franja horaria;
- tasa de fallas técnicas;
- tasa de transferencia a humano, si aplica.

---

# 11. Diseño funcional del dashboard

## 11.1 Estructura sugerida de pantalla

### A. Encabezado
- nombre del cliente;
- rango de fechas;
- filtros principales.

### B. Barra de KPIs
- total calls;
- answered;
- unanswered;
- answer rate;
- avg duration;
- total duration;
- billed minutes;
- active calls.

### C. Gráficos
- tendencia de llamadas por día;
- distribución por estado;
- distribución por agente;
- heatmap de llamadas por día/hora.

### D. Tabla de llamadas recientes
- fecha;
- hora;
- duración;
- agente;
- resumen;
- estado.

---

# 12. Modelo de datos propuesto

## 12.1 Principios del modelo

El modelo de datos de la Fase II deberá cumplir estos principios:

- la fuente de verdad del dashboard será la base de datos interna;
- toda entidad de negocio visible al cliente deberá estar asociada a un `tenant`;
- la identidad externa del usuario será gestionada por Auth0, pero la autorización funcional se resolverá desde el modelo interno;
- los datos de llamadas provenientes de Ultravox deberán persistirse y normalizarse antes de ser usados por el dashboard;
- el modelo deberá soportar crecimiento futuro hacia múltiples organizaciones por usuario, más roles, exportaciones y reportes avanzados;
- el modelo deberá soportar configuración por tenant como mecanismo principal de personalización.

---

## 12.2 Tabla `tenants`

Representa a cada cliente u organización dentro de la plataforma.

### Campos sugeridos
- `id`
- `name`
- `slug`
- `timezone`
- `status`
- `created_at`
- `updated_at`

### Reglas
- cada tenant representa una organización cliente;
- toda llamada, agente, métrica, membresía y configuración deberá asociarse a un tenant;
- `slug` deberá ser único;
- `timezone` se usará para mostrar fechas, horas y agregaciones del dashboard.

---

## 12.3 Tabla `users`

Representa el usuario interno de la plataforma, vinculado a una identidad externa autenticada.

### Campos sugeridos
- `id`
- `external_auth_id`
- `email`
- `name`
- `is_internal`
- `status`
- `last_login_at`
- `created_at`
- `updated_at`

### Reglas
- `external_auth_id` almacenará el identificador del proveedor de identidad, por ejemplo Auth0;
- un usuario autenticado deberá poder resolverse hacia un usuario interno;
- `is_internal = true` identificará usuarios administrativos de plataforma;
- `status` deberá soportar al menos:
  - `active`
  - `inactive`
  - `suspended`

### Restricciones sugeridas
- `external_auth_id` único;
- `email` indexado;
- no se permitirá acceso al dashboard si el usuario no está activo.

---

## 12.4 Tabla `tenant_memberships`

Representa la pertenencia de un usuario a un tenant y su rol dentro de esa organización.

### Campos sugeridos
- `id`
- `tenant_id`
- `user_id`
- `role`
- `status`
- `created_at`
- `updated_at`

### Reglas
- un usuario cliente deberá tener una membresía activa para operar en un tenant;
- el rol del dashboard se resolverá desde esta tabla;
- el modelo deberá soportar que en el futuro un usuario pertenezca a varios tenants.

### Valores sugeridos para `role`
- `platform_admin`
- `tenant_admin`
- `tenant_analyst`
- `tenant_viewer`

### Valores sugeridos para `status`
- `active`
- `inactive`
- `revoked`

### Restricciones sugeridas
- índice por `tenant_id`;
- índice por `user_id`;
- unicidad compuesta recomendada sobre `tenant_id + user_id`.

---

## 12.5 Tabla `agents`

Representa los agentes visibles para el cliente dentro de su organización.

### Campos sugeridos
- `id`
- `tenant_id`
- `external_agent_id`
- `name`
- `channel_type`
- `status`
- `created_at`
- `updated_at`

### Reglas
- cada agente deberá pertenecer a un tenant;
- `external_agent_id` podrá almacenar el identificador del proveedor externo si aplica;
- `channel_type` podrá ayudar a distinguir voz web, voz telefónica, híbrido u otros tipos futuros;
- si una llamada no puede mapearse a un agente, deberá existir lógica de categoría `Sin agente asignado` sin necesidad de crear un agente falso.

### Restricciones sugeridas
- índice por `tenant_id`;
- índice por `external_agent_id`.

---

## 12.6 Tabla `calls`

Tabla principal de llamadas para métricas, trazabilidad y visualización en dashboard.

### Campos sugeridos
- `id`
- `tenant_id`
- `external_call_id`
- `external_provider`
- `agent_id` nullable
- `provider_agent_id` nullable
- `started_at`
- `joined_at` nullable
- `ended_at` nullable
- `duration_seconds`
- `billed_minutes`
- `provider_status`
- `normalized_status`
- `summary`
- `short_summary`
- `recording_url` nullable
- `direction` nullable
- `customer_phone` nullable
- `last_synced_at`
- `created_at`
- `updated_at`

### Reglas
- toda llamada deberá estar asociada a un tenant;
- `external_call_id` conservará el identificador original del proveedor;
- `external_provider` permitirá distinguir orígenes como Ultravox u otros futuros;
- `provider_status` conservará el estado original del proveedor;
- `normalized_status` será el estado oficial usado por el dashboard;
- `summary` y `short_summary` deberán persistirse si están disponibles;
- `duration_seconds` y `billed_minutes` podrán coexistir si la duración real difiere del valor facturado;
- `last_synced_at` permitirá auditoría de sincronización.

### Valores sugeridos para `normalized_status`
- `in_progress`
- `answered`
- `unanswered`
- `rejected`
- `failed`
- `cancelled`
- `transferred`
- `voicemail`

### Restricciones sugeridas
- índice por `tenant_id`;
- índice por `external_call_id`;
- índice por `started_at`;
- índice compuesto recomendado por `tenant_id + started_at`;
- índice recomendado por `tenant_id + normalized_status`;
- índice recomendado por `tenant_id + agent_id`.

---

## 12.7 Tabla `call_events`

Tabla de eventos crudos o normalizados asociados a una llamada, útil para auditoría y depuración.

### Campos sugeridos
- `id`
- `call_id`
- `tenant_id`
- `event_type`
- `provider_event_id` nullable
- `payload_json`
- `received_at`

### Reglas
- esta tabla permitirá conservar trazabilidad de eventos recibidos desde Ultravox;
- deberá permitir reconstruir parcial o totalmente la historia de una llamada;
- `payload_json` almacenará el evento original recibido.

### Restricciones sugeridas
- índice por `call_id`;
- índice por `tenant_id`;
- índice por `received_at`.

---

## 12.8 Tabla `metric_snapshots_daily`

Tabla opcional pero recomendada para agregación y optimización futura del dashboard.

### Campos sugeridos
- `id`
- `tenant_id`
- `date`
- `agent_id` nullable
- `calls_total`
- `calls_answered`
- `calls_unanswered`
- `duration_total_seconds`
- `billed_minutes`
- `created_at`
- `updated_at`

### Reglas
- esta tabla permitirá acelerar consultas de tendencias y KPIs diarios;
- podrá generarse mediante jobs batch o procesos de agregación programada;
- no reemplaza la tabla `calls`, sino que optimiza lectura analítica.

### Restricciones sugeridas
- índice por `tenant_id + date`;
- índice por `tenant_id + agent_id + date`.

---

## 12.9 Tabla `access_audit_logs`

Registra accesos y consultas relevantes para auditoría funcional del módulo.

### Campos sugeridos
- `id`
- `user_id`
- `tenant_id`
- `action`
- `resource`
- `ip_address`
- `user_agent`
- `created_at`

### Reglas
- deberá registrar accesos al dashboard y consultas relevantes;
- permitirá rastrear qué usuario consultó qué tenant y cuándo;
- será especialmente útil para auditoría de accesos administrativos cruzados.

### Ejemplos de `action`
- `login_success`
- `dashboard_view`
- `kpis_view`
- `recent_calls_view`
- `cross_tenant_admin_access`

### Restricciones sugeridas
- índice por `user_id`;
- índice por `tenant_id`;
- índice por `created_at`.

---

## 12.10 Relaciones principales del modelo

### Relaciones obligatorias

- un `tenant` tiene muchos `tenant_memberships`
- un `user` tiene muchas `tenant_memberships`
- un `tenant` tiene muchos `agents`
- un `tenant` tiene muchas `calls`
- un `agent` puede tener muchas `calls`
- una `call` puede tener muchos `call_events`
- un `tenant` puede tener muchos `metric_snapshots_daily`
- un `user` puede tener muchos `access_audit_logs`

### Relación de autorización

La autorización del dashboard deberá resolverse con esta cadena lógica:

```text
identidad externa → user interno → tenant_membership activa → tenant activo → permisos sobre métricas y llamadas
```

---

## 12.11 Consideraciones de diseño

### Desacoplamiento del proveedor de identidad
Aunque Auth0 sea el proveedor de identidad, la plataforma no deberá depender exclusivamente de sus claims para la lógica de negocio. Por eso `users` y `tenant_memberships` son obligatorios.

### Desacoplamiento del proveedor de llamadas
Aunque Ultravox provea los datos crudos de llamadas, la tabla `calls` será la fuente interna oficial del dashboard.

### Preparación para crecimiento futuro
El modelo deberá permitir evolución futura hacia:
- múltiples tenants por usuario;
- permisos granulares;
- exportación de reportes;
- dashboards por canal;
- dashboards por campaña;
- múltiples proveedores de voz;
- scoring y analítica avanzada;
- configuraciones más profundas por tenant.

---

## 12.12 Reglas mínimas de integridad

- ninguna llamada visible en dashboard podrá existir sin `tenant_id`;
- ningún usuario cliente podrá operar sin membresía activa;
- ninguna métrica del dashboard podrá calcularse fuera del tenant resuelto;
- toda llamada deberá conservar identificador interno único;
- toda llamada sincronizada deberá conservar referencia al identificador externo del proveedor cuando exista;
- la tabla `calls` deberá permitir coexistencia entre estado original y estado normalizado.

---

# 13. Integración con Ultravox

## 13.1 Ingesta en tiempo real
El backend deberá procesar webhooks como:
- inicio de llamada;
- unión a llamada;
- finalización de llamada;
- facturación;
- resumen, si llega por evento o consulta.

## 13.2 Backfill y reconciliación
El backend deberá ejecutar jobs para:
- recuperar eventos perdidos;
- completar resúmenes;
- completar estados finales;
- completar duración y billed minutes;
- validar consistencia histórica.

## 13.3 Regla de consulta
El dashboard leerá únicamente desde la base de datos interna.

---

# 14. Modelo de identidad y usuario

## 14.1 Identidad externa
Cada usuario autenticado tendrá una identidad externa provista por Auth0.

Campo lógico esperado:
- `external_auth_id`

Ejemplo conceptual:
- `auth0|abc123xyz`

## 14.2 Usuario interno
Además de la identidad externa, todo usuario deberá tener representación interna en la base de datos del sistema.

El usuario interno permitirá:
- asociarlo a un tenant;
- asignarle un rol;
- auditarlo;
- controlar su estado;
- desacoplar el producto del proveedor de identidad.

## 14.3 Regla de sincronización
La primera vez que un usuario autenticado válido entre al sistema, el backend deberá:
1. identificar el `external_auth_id`;
2. buscar si ya existe usuario interno;
3. si no existe, crearlo o dejarlo pendiente según política;
4. asociarlo al tenant que corresponda;
5. asignarle un rol inicial según reglas del negocio.

---

# 15. Modelo multicliente

## 15.1 Tenant
Cada cliente de la plataforma será representado por un `tenant`.

## 15.2 Membresía
La relación entre usuario y tenant se gestionará mediante una entidad de membresía.

Un usuario podrá:
- pertenecer a un tenant;
- tener un rol dentro del tenant;
- en fases futuras, pertenecer a varios tenants.

## 15.3 Tenant activo
Para la Fase II se asume, salvo evolución posterior, que un usuario cliente operará sobre un único tenant activo.

Si en fases futuras un usuario tiene múltiples tenants, el sistema deberá incorporar selección de tenant activo antes de entrar al dashboard.

---

# 16. Modelo de roles

## 16.1 Roles internos requeridos

### `platform_admin`
Usuario interno de plataforma con acceso transversal para soporte y auditoría.

### `tenant_admin`
Usuario administrador del cliente.

### `tenant_analyst`
Usuario analista del cliente.

### `tenant_viewer`
Usuario cliente con acceso de solo lectura.

## 16.2 Resolución de rol
El rol visible para la aplicación deberá resolverse desde la base de datos interna, no depender exclusivamente de claims del proveedor externo.

## 16.3 Regla de autorización
Toda autorización del dashboard deberá evaluarse con base en:
- identidad autenticada;
- usuario interno válido;
- tenant activo válido;
- rol interno válido.

---

# 17. Tenant configuration layer

## 17.1 Objetivo
Permitir variaciones de negocio por cliente sin duplicar el backend.

## 17.2 Capacidades mínimas esperadas
La capa de configuración por tenant deberá poder definir:
- agentes activos;
- prompts;
- workflows;
- reglas de enrutamiento;
- reglas de handoff;
- CRM asociado;
- calendarios;
- webhooks;
- campos personalizados;
- etiquetas o clasificaciones internas.

## 17.3 Regla de diseño
La configuración por tenant deberá modelarse como datos y configuración versionable cuando sea posible, no como forks del código del backend.

---

# 18. Flujos de autenticación y acceso

## 18.1 Login web

### Flujo esperado
1. El usuario entra a una ruta protegida del dashboard.
2. Si no tiene sesión válida, el frontend lo redirige al flujo de login.
3. Auth0 autentica al usuario.
4. El usuario vuelve a la app con sesión/tokens válidos.
5. El frontend obtiene contexto de usuario autenticado.
6. El backend valida la identidad y resuelve usuario interno + tenant + rol.
7. Si todo es válido, el usuario entra al dashboard.

## 18.2 Logout web

### Flujo esperado
1. El usuario hace logout.
2. Se cierra sesión local.
3. Se cierra sesión con el proveedor de identidad.
4. El usuario es redirigido a una ruta pública.

## 18.3 Acceso sin membresía

### Flujo esperado
1. El usuario logra autenticarse correctamente.
2. El backend no encuentra membresía válida sobre tenant.
3. El acceso al dashboard se bloquea.
4. El sistema muestra una vista controlada de “sin acceso” o “sin organización asignada”.

---

# 19. Protección de rutas y endpoints

## 19.1 Rutas públicas
Ejemplos:
- landing;
- páginas informativas;
- contacto.

## 19.2 Rutas privadas
Ejemplos:
- `/dashboard`
- `/dashboard/calls`
- `/dashboard/agents`
- `/dashboard/reports`

## 19.3 Regla de protección
Las rutas privadas deberán requerir sesión autenticada válida.

## 19.4 Regla de autorización final
Aunque el frontend proteja rutas, la autorización definitiva deberá hacerse siempre en backend.

## 19.5 Todos los endpoints privados deberán:

1. validar token o contexto autenticado;
2. resolver `external_auth_id`;
3. buscar usuario interno;
4. resolver tenant activo;
5. validar membresía activa;
6. validar rol;
7. filtrar la data por `tenant_id`.

## 19.6 Ningún endpoint del dashboard devolverá datos si falla alguno de esos pasos.

## 19.7 Ejemplos de endpoints protegidos
- `GET /api/v1/dashboard/kpis`
- `GET /api/v1/dashboard/trends`
- `GET /api/v1/dashboard/recent-calls`
- `GET /api/v1/dashboard/heatmap`
- `GET /api/v1/dashboard/agent-distribution`

---

# 20. Dependencias de autorización en FastAPI

## 20.1 Se deberá implementar una dependencia reusable de seguridad
Ejemplo lógico:
- `get_current_user()`
- `get_current_membership()`
- `require_role(...)`

## 20.2 Responsabilidades de la dependencia
- validar token;
- extraer identidad externa;
- buscar usuario interno;
- buscar membresía activa;
- adjuntar contexto del tenant;
- rechazar acceso si la validación falla.

## 20.3 Contexto esperado por request
Cada request privada deberá poder contar con:
- `current_user`
- `current_tenant`
- `current_role`

---

# 21. Resolución del tenant y del usuario interno

## 21.1 Regla base
El tenant no deberá confiarse a un parámetro arbitrario enviado por frontend.

## 21.2 Forma de resolución
Para Fase II, el tenant deberá resolverse desde la membresía del usuario autenticado.

## 21.3 Regla de seguridad
Aunque el frontend mande filtros o parámetros, el backend deberá imponer el `tenant_id` autorizado desde el contexto autenticado.

## 21.4 Reglas para el usuario interno
El backend deberá ser capaz de:
- encontrar usuario por `external_auth_id`;
- crearlo si la política lo permite;
- bloquear acceso si no hay usuario interno válido.

## 21.5 Política recomendada
Para esta fase, se recomienda:
- permitir creación controlada del usuario interno;
- pero no conceder acceso al dashboard si no existe membresía activa sobre un tenant.

---

# 22. API interna propuesta

## 22.1 KPIs
`GET /api/v1/dashboard/kpis`

Parámetros:
- `from`
- `to`
- `agent_id`
- `status`

Respuesta sugerida:
```json
{
  "calls_total": 1200,
  "calls_answered": 950,
  "calls_unanswered": 250,
  "answer_rate": 79.1,
  "avg_duration_seconds": 183,
  "total_duration_seconds": 173850,
  "billed_minutes": 3097,
  "active_calls": 3
}
```

## 22.2 Tendencia
`GET /api/v1/dashboard/trends`

Respuesta sugerida:
```json
{
  "series": [
    { "date": "2026-04-01", "calls_total": 35, "calls_answered": 28 },
    { "date": "2026-04-02", "calls_total": 41, "calls_answered": 33 }
  ]
}
```

## 22.3 Distribución por estado
`GET /api/v1/dashboard/status-distribution`

## 22.4 Distribución por agente
`GET /api/v1/dashboard/agent-distribution`

## 22.5 Heatmap
`GET /api/v1/dashboard/heatmap`

Respuesta sugerida:
```json
{
  "matrix": [
    { "day": "monday", "hour": 9, "calls": 12 },
    { "day": "monday", "hour": 10, "calls": 18 }
  ]
}
```

## 22.6 Llamadas recientes
`GET /api/v1/dashboard/recent-calls`

Parámetros:
- `from`
- `to`
- `agent_id`
- `status`
- `page`
- `page_size`

Respuesta sugerida:
```json
{
  "items": [
    {
      "id": "call_001",
      "started_at": "2026-04-10T10:20:00-05:00",
      "duration_seconds": 245,
      "agent_name": "Agente Ventas 1",
      "summary": "Cliente solicitó agendamiento de demostración.",
      "status": "answered"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 245
}
```

## 22.7 Perfil actual
`GET /api/v1/me`

Respuesta sugerida:
```json
{
  "user_id": "usr_001",
  "email": "cliente@empresa.com",
  "name": "Juan Pérez",
  "tenant_id": "tenant_001",
  "tenant_name": "Empresa Demo",
  "role": "tenant_admin",
  "is_internal": false
}
```

---

# 23. Orden recomendado de implementación

## 23.1 Secuencia recomendada
La construcción de la Fase II deberá seguir este orden:

1. documentación consolidada;
2. autenticación, tenant y roles;
3. modelo de datos;
4. ingesta y normalización de llamadas;
5. API interna del dashboard;
6. frontend del dashboard;
7. QA y hardening.

## 23.2 Regla de construcción
No se deberá construir primero el frontend del dashboard sin contar antes con:
- autenticación;
- tenant isolation;
- modelo de datos;
- contratos de API;
- fuente de verdad en backend.

## 23.3 Regla de refactor
La evolución del backend actual deberá hacerse mediante refactor selectivo e incremental, no mediante reescritura total sin necesidad.

---

# 24. Auditoría y trazabilidad

## 24.1 Eventos a auditar
- login exitoso;
- acceso al dashboard;
- consulta de métricas;
- consulta de llamadas recientes;
- accesos administrativos cruzados entre tenants;
- fallos de autorización.

## 24.2 Objetivo
Poder responder:
- quién accedió;
- a qué tenant;
- cuándo;
- con qué rol;
- qué recurso consultó.

---

# 25. Requerimientos no funcionales

## RNF-001 Rendimiento
Las consultas del dashboard deberán responder de forma fluida para rangos comunes de 7, 30 y 90 días.

## RNF-002 Escalabilidad
La arquitectura deberá soportar múltiples clientes y múltiples agentes por cliente.

## RNF-003 Trazabilidad
Toda llamada deberá ser auditable por identificador interno y externo.

## RNF-004 Consistencia
Los KPIs, gráficos y tabla deberán calcularse con la misma lógica y filtros.

## RNF-005 Extensibilidad
La solución deberá permitir añadir nuevas métricas en fases posteriores sin rediseño mayor.

## RNF-AUTH-001
El acceso al dashboard deberá resolverse de forma segura y consistente.

## RNF-AUTH-002
La validación de autenticación y autorización deberá ser reusable entre endpoints.

## RNF-AUTH-003
El modelo deberá soportar crecimiento futuro hacia múltiples organizaciones por usuario.

## RNF-AUTH-004
La plataforma deberá desacoplar identidad externa de lógica de negocio interna.

## RNF-AUTH-005
La revocación de membresía deberá impedir el acceso posterior al dashboard.

---

# 26. Estados vacíos y manejo de errores

## RF-037
Si no existen llamadas en el rango filtrado, el dashboard deberá mostrar estados vacíos claros y útiles.

## RF-038
Si falta resumen, el sistema deberá mostrar texto controlado.

## RF-039
Si un gráfico no tiene datos, deberá mantenerse visible con mensaje de ausencia de información.

## RF-040
Si falla la carga de métricas, el frontend deberá mostrar un mensaje de error controlado y opción de reintento.

---

# 27. Criterios de aceptación

## CA-001
Un cliente autenticado puede entrar y ver solo sus métricas.

## CA-002
Los KPIs cambian correctamente con filtros.

## CA-003
La tabla de llamadas recientes muestra fecha, duración, agente, resumen y estado.

## CA-004
El sistema soporta al menos filtros por fecha, agente y estado.

## CA-005
Los datos del dashboard provienen del backend interno y no del frontend consultando Ultravox.

## CA-006
Las llamadas pueden asociarse a agente o a categoría controlada de no asignación.

## CA-007
Los estados de llamada están normalizados y se usan para métricas consistentes.

## CA-008
Las llamadas en curso no se contabilizan incorrectamente como finalizadas.

## CA-009
La arquitectura queda lista para crecimiento futuro.

## CA-AUTH-001
Un usuario autenticado puede acceder al dashboard solo si existe usuario interno válido y membresía activa.

## CA-AUTH-002
Un usuario de un tenant no puede consultar datos de otro tenant.

## CA-AUTH-003
El backend nunca devuelve datos del dashboard sin resolver tenant y rol.

## CA-AUTH-004
Los endpoints privados del dashboard están protegidos y reutilizan la misma lógica de autorización.

## CA-AUTH-005
La plataforma conserva trazabilidad mínima de accesos y consultas.

## CA-AUTH-006
El sistema queda preparado para crecimiento futuro sin rehacer la base de identidad y permisos.

---

# 28. Riesgos y mitigaciones

## Riesgo 1
Eventos perdidos o retrasados desde Ultravox.

**Mitigación:** reconciliación y sync jobs.

## Riesgo 2
Diferencia entre duración real y minutos facturados.

**Mitigación:** persistir ambos valores y mostrar lógica explícita.

## Riesgo 3
Altos volúmenes de consultas históricas.

**Mitigación:** índices, agregados diarios y optimización por snapshots futuros.

## Riesgo 4
Definiciones ambiguas de llamada contestada.

**Mitigación:** establecer lógica normalizada en backend desde el inicio.

## Riesgo 5
Usuario autenticado sin membresía interna válida.

**Mitigación:** bloquear acceso y mostrar estado controlado.

## Riesgo 6
Confundir claims del proveedor con permisos de negocio definitivos.

**Mitigación:** resolver siempre rol y tenant desde base interna.

## Riesgo 7
Exponer datos por parámetros manipulados desde frontend.

**Mitigación:** imponer `tenant_id` desde contexto autenticado backend.

## Riesgo 8
Acoplar toda la aplicación a un proveedor externo.

**Mitigación:** mantener `users`, `tenants` y `tenant_memberships` en base propia.

## Riesgo 9
Intentar resolver personalización por cliente duplicando el backend.

**Mitigación:** adoptar configuración por tenant y extensiones por excepción.

---

# 29. Resultado esperado de la Fase II

Al finalizar esta fase, la plataforma deberá contar con un dashboard multicliente que permita a cada cliente:

- monitorear su operación de llamadas;
- entender desempeño por agente;
- revisar tendencias;
- consultar llamadas recientes;
- apoyarse en métricas confiables calculadas desde el backend propio.

La plataforma quedará además preparada para:

- login seguro con proveedor externo;
- resolución robusta de tenant;
- gestión consistente de usuarios cliente;
- control de acceso por rol;
- protección real del dashboard multicliente;
- futura expansión hacia administración avanzada de organizaciones;
- exportaciones;
- métricas comparativas;
- alertas;
- dashboards ejecutivos;
- módulos de facturación o performance avanzada;
- evolución del producto como plataforma central multitenant.
