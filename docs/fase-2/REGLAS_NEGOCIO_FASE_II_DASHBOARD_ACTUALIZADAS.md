# Reglas de negocio actualizadas
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.2  
**Estado:** Documento consolidado de negocio  
**Contexto arquitectónico:** plataforma central multitenant con backend propio como fuente de verdad del dashboard, Auth0 como proveedor externo de identidad y Ultravox como fuente upstream de eventos y datos crudos.

---

# 1. Propósito y alcance del módulo

**RN-001.** La plataforma deberá ofrecer un dashboard de métricas que permita a cada cliente consultar el desempeño de sus agentes de voz y de sus llamadas.

**RN-002.** El dashboard será un módulo de consulta y análisis; en esta fase no permitirá editar llamadas, agentes, resúmenes ni métricas.

**RN-003.** El dashboard deberá mostrar información histórica y del periodo filtrado por el usuario.

**RN-004.** El dashboard deberá estar disponible solo para usuarios autenticados y autorizados.

---

# 2. Estrategia de plataforma y arquitectura de negocio

**RN-005.** La solución deberá construirse como una plataforma central multitenant y no como un backend independiente por cada negocio como estrategia base.

**RN-006.** La lógica transversal del producto deberá vivir en un backend compartido para todos los clientes.

**RN-007.** La personalización por negocio deberá resolverse principalmente mediante configuración por tenant y no mediante duplicación del backend.

**RN-008.** Solo en casos excepcionales de alta especialización, regulación o infraestructura dedicada se permitirá una extensión o despliegue aislado por cliente.

**RN-009.** El dashboard de métricas deberá operar sobre un modelo de datos canónico compartido para todos los tenants.

**RN-010.** La plataforma deberá diferenciar entre:
- core compartido;
- configuración por tenant;
- capa de integraciones;
- extensiones especiales cuando un caso lo requiera.

---

# 3. Fuente oficial de datos del dashboard

**RN-011.** La fuente oficial de verdad del dashboard será la base de datos de la plataforma, administrada por el backend propio.

**RN-012.** El frontend del dashboard no deberá consultar directamente APIs de Ultravox para construir métricas visibles al cliente.

**RN-013.** Los datos crudos de llamadas podrán ser obtenidos desde Ultravox mediante webhooks, sincronización programada o procesos de conciliación.

**RN-014.** El backend deberá recibir, transformar, normalizar y almacenar los datos provenientes de Ultravox antes de exponerlos al dashboard.

**RN-015.** Todas las métricas visibles al cliente deberán calcularse sobre datos persistidos y normalizados en la base de datos interna.

**RN-016.** El dashboard solo podrá consultar APIs internas del backend propio.

---

# 4. Sincronización e integración con Ultravox

**RN-017.** El sistema deberá soportar la recepción de eventos de llamadas desde Ultravox para actualizar los registros internos.

**RN-018.** El sistema deberá contar con un mecanismo de reconciliación o resíncronización para recuperar llamadas, estados o resúmenes que no hayan llegado correctamente en tiempo real.

**RN-019.** Si existe un desfase temporal entre Ultravox y la base interna, el dashboard mostrará la información disponible en la base local hasta completar la sincronización.

**RN-020.** La indisponibilidad temporal de Ultravox no deberá impedir la consulta del dashboard histórico ya persistido.

**RN-021.** Si un dato de llamada aún no ha sido sincronizado completamente, el sistema deberá marcarlo como pendiente o en procesamiento sin romper los cálculos globales.

---

# 5. Multicliente y aislamiento de información

**RN-022.** La plataforma deberá operar en modo multicliente.

**RN-023.** Toda llamada, resumen, métrica, agente, configuración y agregado deberá estar asociado a un `tenant` o cliente.

**RN-024.** Cada cliente solo podrá visualizar información perteneciente a su propia organización.

**RN-025.** Ningún usuario cliente podrá consultar llamadas o métricas de otro cliente, aunque conozca identificadores internos o URLs.

**RN-026.** Toda consulta del dashboard deberá filtrar por el tenant autenticado antes de devolver resultados.

**RN-027.** La plataforma deberá resolver el tenant activo desde el backend y no confiar en parámetros arbitrarios enviados por frontend.

---

# 6. Identidad y autenticación

**RN-028.** La plataforma deberá usar un proveedor externo de identidad para autenticar usuarios.

**RN-029.** La autenticación no deberá ser implementada manualmente como mecanismo principal del producto.

**RN-030.** El sistema deberá soportar inicio de sesión seguro para usuarios internos y usuarios cliente.

**RN-031.** El sistema deberá permitir cierre de sesión seguro.

**RN-032.** El sistema deberá permitir recuperación de acceso mediante los mecanismos provistos por el proveedor de identidad.

**RN-033.** Ningún usuario no autenticado podrá acceder a rutas, vistas o endpoints del dashboard.

**RN-034.** La autenticación y la autorización deberán tratarse como procesos distintos.

**RN-035.** El proveedor externo de identidad resolverá la autenticación del usuario.

**RN-036.** El backend propio resolverá la autorización funcional del usuario sobre datos, vistas y acciones.

---

# 7. Organizaciones, tenant y membresía

**RN-037.** Cada cliente deberá estar representado internamente como un tenant u organización.

**RN-038.** Cada usuario cliente deberá pertenecer a un tenant válido para acceder al dashboard.

**RN-039.** El acceso a métricas, llamadas y agentes deberá resolverse siempre dentro del tenant activo del usuario autenticado.

**RN-040.** Un usuario no podrá operar sobre un tenant al que no pertenezca.

**RN-041.** El sistema deberá mantener una relación interna entre:
- identidad externa autenticada;
- usuario interno;
- tenant;
- rol de negocio.

**RN-042.** Si un usuario autenticado no tiene tenant asignado, no deberá acceder al dashboard de cliente.

**RN-043.** Si un usuario pertenece a más de una organización en fases futuras, el sistema deberá permitir resolver el tenant activo antes de mostrar información.

---

# 8. Usuario interno y usuario cliente

**RN-044.** La plataforma deberá diferenciar entre usuarios internos de plataforma y usuarios cliente.

**RN-045.** Los usuarios internos podrán operar con permisos ampliados según su rol.

**RN-046.** Los usuarios cliente solo podrán acceder a la información y acciones autorizadas dentro de su tenant.

**RN-047.** Todo usuario autenticado deberá contar con un registro interno en la base de datos o con un mecanismo de sincronización que permita representarlo internamente.

**RN-048.** La plataforma deberá poder vincular el identificador del proveedor de identidad con el identificador interno del usuario.

---

# 9. Roles del sistema

**RN-049.** La plataforma deberá soportar al menos los siguientes roles de negocio:
- `platform_admin`
- `tenant_admin`
- `tenant_analyst`
- `tenant_viewer`

**RN-050.** El rol `platform_admin` podrá consultar información de cualquier tenant con fines operativos, de soporte y auditoría.

**RN-051.** El rol `tenant_admin` podrá visualizar toda la información analítica de su organización y gestionar aspectos autorizados del tenant en fases futuras.

**RN-052.** El rol `tenant_analyst` podrá consultar métricas, gráficos, filtros y tabla de llamadas de su tenant.

**RN-053.** El rol `tenant_viewer` podrá consultar información permitida del dashboard, con permisos de solo lectura.

**RN-054.** El sistema deberá permitir evolución futura hacia permisos más granulares sin romper el modelo base de roles.

---

# 10. Autorización y control de acceso

**RN-055.** La autorización del dashboard deberá evaluarse con base en:
- identidad autenticada;
- tenant activo;
- rol interno de negocio;
- permisos internos de la plataforma.

**RN-056.** Ningún dato del dashboard deberá devolverse al frontend sin validación previa del tenant y del rol del usuario.

**RN-057.** Todo endpoint del dashboard deberá validar que el usuario autenticado tenga permisos suficientes para consultar la información solicitada.

**RN-058.** El frontend no deberá decidir por sí solo la autorización final del usuario; la validación definitiva deberá ejecutarse en backend.

**RN-059.** Si no es posible resolver el tenant o el rol del usuario, el acceso deberá bloquearse de forma segura.

---

# 11. Gestión de usuarios cliente

**RN-060.** La plataforma deberá soportar usuarios cliente asociados a una organización específica.

**RN-061.** La plataforma deberá quedar preparada para flujos futuros de invitación de usuarios a una organización cliente.

**RN-062.** La plataforma deberá quedar preparada para activación, desactivación y revocación de acceso de usuarios cliente.

**RN-063.** Si un usuario cliente es desactivado o pierde membresía sobre una organización, deberá perder acceso al dashboard de ese tenant.

**RN-064.** El sistema deberá registrar internamente el estado de usuario, al menos con categorías:
- activo
- inactivo
- suspendido

---

# 12. Configuración por tenant

**RN-065.** La plataforma deberá permitir personalización por tenant sin necesidad de duplicar el backend.

**RN-066.** La configuración por tenant deberá poder abarcar como mínimo:
- agentes;
- prompts;
- workflows;
- reglas de routing;
- reglas de handoff;
- calendarios;
- CRM;
- etiquetas;
- campos personalizados;
- webhooks o adaptadores específicos.

**RN-067.** La configuración de un tenant no deberá afectar el comportamiento ni los datos de otros tenants.

**RN-068.** El core compartido deberá ser capaz de soportar distintos casos de uso mediante configuración y no únicamente mediante código específico por cliente.

---

# 13. Modelo mínimo de llamada

**RN-069.** Toda llamada deberá tener un identificador interno único.

**RN-070.** Toda llamada deberá conservar también el identificador original del proveedor externo cuando aplique.

**RN-071.** Toda llamada deberá registrar al menos:
- tenant
- fecha y hora de inicio
- fecha y hora de fin, si existe
- duración
- agente asociado, si aplica
- estado original del proveedor
- estado normalizado interno
- resumen, si existe
- timestamps de creación y última actualización

**RN-072.** El sistema deberá conservar la trazabilidad de sincronización de cada llamada.

---

# 14. Estado normalizado de llamada

**RN-073.** Toda llamada deberá registrar un estado normalizado interno para asegurar consistencia analítica.

**RN-074.** El sistema deberá soportar como mínimo estos estados normalizados:
- En curso
- Contestada
- No contestada
- Rechazada
- Fallida
- Cancelada
- Transferida
- Buzón de voz, si aplica técnicamente

**RN-075.** Una llamada solo podrá tener un estado final de cierre, salvo que aún esté en curso.

**RN-076.** El sistema podrá almacenar simultáneamente:
- el estado original del proveedor
- el estado normalizado interno

**RN-077.** Las métricas del dashboard deberán usar siempre el estado normalizado interno.

---

# 15. Asociación por agente

**RN-078.** Toda llamada deberá quedar asociada a un agente cuando técnicamente sea posible.

**RN-079.** Si una llamada no puede asociarse a un agente específico, deberá clasificarse como `Sin agente asignado` o equivalente.

**RN-080.** Las métricas por agente no deberán excluir llamadas sin asignación; estas deberán agruparse en una categoría controlada.

---

# 16. Resumen de llamada

**RN-081.** El sistema deberá almacenar el resumen de llamada cuando el proveedor o el backend lo generen correctamente.

**RN-082.** El resumen deberá quedar asociado a la llamada para consulta posterior.

**RN-083.** El resumen deberá ser visible solo para usuarios autorizados del mismo cliente.

**RN-084.** Si una llamada no contestada no tiene resumen, el sistema podrá mostrar un valor controlado como:
- `Sin resumen`
- `Resumen no disponible`

**RN-085.** La ausencia de resumen no invalidará la llamada para el cálculo de métricas.

---

# 17. Métricas mínimas del dashboard

**RN-086.** El dashboard deberá mostrar como mínimo:
- llamadas totales del periodo
- llamadas contestadas
- llamadas no contestadas
- tasa de contestación
- duración promedio de llamadas contestadas
- duración total acumulada
- minutos totales consumidos
- minutos facturados, si aplica
- llamadas en curso
- distribución de llamadas por agente
- volumen de llamadas por día y hora
- tabla de llamadas recientes

**RN-087.** La métrica `llamadas totales` deberá incluir todas las llamadas del periodo filtrado, independientemente de su estado final.

**RN-088.** La métrica `llamadas contestadas` deberá incluir solo llamadas con conexión efectiva según la lógica definida por la plataforma.

**RN-089.** La métrica `llamadas no contestadas` deberá incluir llamadas sin conexión efectiva según el estado normalizado.

**RN-090.** La tasa de contestación se calculará como:

```text
llamadas contestadas / llamadas totales elegibles * 100
```

**RN-091.** La duración promedio deberá calcularse únicamente sobre llamadas contestadas, salvo definición futura distinta.

**RN-092.** Los minutos facturados podrán diferir de la duración real si existen reglas de redondeo, mínimos facturables o políticas del proveedor, pero el valor visible al cliente deberá salir desde la base interna.

---

# 18. Métricas recomendadas adicionales

**RN-093.** El sistema deberá estar preparado para mostrar tasa de transferencia a humano, si el flujo la soporta.

**RN-094.** El sistema deberá estar preparado para mostrar llamadas fallidas por error técnico.

**RN-095.** El sistema deberá estar preparado para mostrar porcentaje de llamadas por estado.

**RN-096.** El sistema deberá estar preparado para mostrar top de agentes por volumen de llamadas.

**RN-097.** El sistema deberá estar preparado para mostrar top de agentes por duración gestionada.

**RN-098.** El sistema deberá estar preparado para mostrar tendencia comparativa contra el periodo anterior.

**RN-099.** El sistema deberá estar preparado para mostrar horas pico de operación.

---

# 19. Tabla de llamadas recientes

**RN-100.** El dashboard deberá incluir una tabla de llamadas recientes.

**RN-101.** Cada fila deberá mostrar como mínimo:
- fecha
- hora
- duración
- nombre del agente
- resumen
- estado de la llamada

**RN-102.** La tabla deberá ordenarse por fecha y hora descendente por defecto.

**RN-103.** La tabla deberá permitir paginación o carga incremental.

**RN-104.** La tabla deberá respetar exactamente los filtros activos del dashboard.

---

# 20. Filtros y segmentación

**RN-105.** El dashboard deberá permitir filtrar por rango de fechas.

**RN-106.** El dashboard deberá incluir filtros rápidos como:
- Hoy
- Últimos 7 días
- Últimos 30 días
- Este mes
- Rango personalizado

**RN-107.** El dashboard deberá permitir filtrar por agente.

**RN-108.** El dashboard deberá permitir filtrar por estado de llamada.

**RN-109.** Todas las tarjetas KPI, gráficos y tablas deberán actualizarse coherentemente al aplicar filtros.

---

# 21. Zona horaria

**RN-110.** Todas las fechas, horas y agregaciones deberán mostrarse en la zona horaria configurada para el cliente.

**RN-111.** Si el cliente no tiene zona horaria configurada, el sistema deberá usar una zona por defecto definida por la plataforma.

---

# 22. Actualización y frescura de datos

**RN-112.** El módulo no requiere exactitud estrictamente en tiempo real, pero deberá manejar una actualización razonable para operación analítica.

**RN-113.** Las llamadas en curso podrán reflejarse mediante refresco periódico o actualización casi real-time.

**RN-114.** Las métricas agregadas no deberán quedar inconsistentes respecto a la tabla y filtros del mismo periodo.

**RN-115.** Una llamada en curso no deberá contabilizarse como no contestada ni como finalizada hasta que reciba estado de cierre.

---

# 23. Visualizaciones

**RN-116.** El dashboard deberá presentar KPIs resumidos en la parte superior.

**RN-117.** El dashboard deberá presentar tendencias del periodo.

**RN-118.** El dashboard deberá mostrar volumen de llamadas por día y hora mediante una visualización tipo heatmap o equivalente.

**RN-119.** El dashboard deberá mostrar distribución de llamadas por agente mediante gráfico circular o equivalente.

**RN-120.** El dashboard deberá mantener consistencia visual entre filtros, KPIs, gráficos y tablas.

---

# 24. Integridad, auditoría y trazabilidad

**RN-121.** Ningún usuario cliente podrá eliminar llamadas desde el dashboard en esta fase.

**RN-122.** El sistema deberá conservar trazabilidad suficiente para auditar cómo se calculó cada métrica relevante.

**RN-123.** La plataforma deberá registrar la fecha de última sincronización o actualización de cada llamada.

**RN-124.** Toda llamada deberá poder vincularse internamente a:
- tenant
- agente
- proveedor de origen
- estado
- timestamps relevantes

**RN-125.** La plataforma deberá registrar eventos relevantes de acceso al menos a nivel de:
- usuario autenticado;
- tenant consultado;
- fecha y hora;
- tipo de acceso o consulta.

**RN-126.** La plataforma deberá poder auditar qué usuario consultó información de métricas de un tenant.

**RN-127.** Los accesos administrativos cruzados entre tenants deberán quedar trazables para fines de soporte y auditoría.

---

# 25. Exportación y evolución futura

**RN-128.** El módulo deberá quedar preparado para exportación futura de reportes por periodo.

**RN-129.** Si se implementa exportación en esta fase o en una posterior, esta deberá respetar exactamente los filtros activos.

**RN-130.** El modelo deberá permitir crecimiento futuro hacia dashboards por:
- campaña
- canal
- número telefónico
- agente
- flujo o skill
- cliente

**RN-131.** El diseño del módulo deberá soportar múltiples agentes por cliente sin rediseño estructural.

**RN-132.** El sistema deberá permitir incorporar nuevas métricas en fases posteriores sin romper la estructura analítica base.

---

# 26. Regla estratégica final

**RN-133.** La plataforma usará un proveedor externo de identidad para autenticar usuarios, pero la lógica de negocio de tenant, roles y permisos será resuelta por el backend propio.

**RN-134.** Ultravox será la fuente de eventos y datos crudos de llamadas; el backend propio será la fuente de verdad operativa y analítica del dashboard.

**RN-135.** La arquitectura objetivo de negocio para la Fase II será una plataforma central multitenant con configuración por tenant y extensiones por excepción, no una colección de backends independientes por cliente.
