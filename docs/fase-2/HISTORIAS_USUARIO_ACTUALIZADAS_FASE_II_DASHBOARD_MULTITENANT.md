# Historias de usuario actualizadas
## Fase II – Dashboard de métricas para clientes
### Proyecto: ServiGlobal · IA / Servi-IA

**Versión:** 1.2  
**Estado:** Backlog funcional actualizado  
**Contexto:** plataforma central multitenant con backend propio como fuente de verdad, Auth0 para identidad, Ultravox como fuente upstream y configuración por tenant como mecanismo principal de personalización.

---

# Épica 1. Autenticación y acceso al dashboard

## HU-001. Acceso autenticado al dashboard
**Como** usuario de la plataforma  
**Quiero** iniciar sesión de forma segura  
**Para** acceder al dashboard de métricas según mis permisos.

### Criterios de aceptación
- El sistema debe redirigir al flujo de autenticación si el usuario no tiene sesión válida.
- Una vez autenticado, el usuario debe regresar a la aplicación con sesión activa.
- Si la autenticación falla, el sistema no debe permitir acceso al dashboard.
- El dashboard no debe ser visible para usuarios no autenticados.

---

## HU-002. Resolución del usuario interno
**Como** sistema  
**Quiero** resolver el usuario autenticado contra un usuario interno  
**Para** poder determinar tenant, rol y permisos de negocio.

### Criterios de aceptación
- El backend debe leer la identidad externa autenticada.
- El backend debe buscar el usuario interno correspondiente.
- Si el usuario interno no existe, el sistema debe aplicar la política definida: crear registro o bloquear acceso.
- Ningún endpoint del dashboard debe responder si no existe usuario interno válido.

---

## HU-003. Acceso solo con membresía válida
**Como** usuario cliente  
**Quiero** acceder al dashboard solo si pertenezco a una organización válida  
**Para** consultar únicamente la información de mi empresa.

### Criterios de aceptación
- El sistema debe validar que el usuario tenga membresía activa en un tenant.
- Si no existe membresía activa, el sistema debe bloquear el acceso.
- El sistema debe mostrar una respuesta controlada de “sin acceso” o equivalente.
- No se debe exponer información parcial del dashboard si no hay membresía válida.

---

# Épica 2. Plataforma multitenant y aislamiento por tenant

## HU-004. Aislamiento de datos por cliente
**Como** cliente de la plataforma  
**Quiero** ver solo mis llamadas y métricas  
**Para** proteger la confidencialidad de mi operación.

### Criterios de aceptación
- Todas las consultas del dashboard deben estar filtradas por `tenant_id`.
- Un usuario cliente no puede ver datos de otro tenant.
- El backend no debe confiar en parámetros manipulados por frontend para cambiar tenant.
- Toda respuesta del dashboard debe construirse desde el tenant resuelto en backend.

---

## HU-005. Acceso administrativo interno
**Como** administrador interno de plataforma  
**Quiero** poder consultar dashboards de distintos clientes  
**Para** brindar soporte y auditoría operativa.

### Criterios de aceptación
- El rol `platform_admin` puede acceder a información de cualquier tenant.
- El acceso debe quedar auditado.
- El sistema debe diferenciar claramente entre acceso interno y acceso cliente.
- Un usuario no interno no puede usar capacidades de acceso cruzado.

---

## HU-006. Acceso según rol
**Como** sistema  
**Quiero** restringir vistas y recursos según el rol del usuario  
**Para** garantizar control de acceso consistente.

### Criterios de aceptación
- El sistema debe resolver el rol desde la base de datos interna.
- El rol `tenant_admin` debe poder ver el dashboard completo de su tenant.
- El rol `tenant_analyst` debe poder consultar métricas y llamadas.
- El rol `tenant_viewer` debe tener acceso de solo lectura a las vistas permitidas.
- Todo endpoint privado debe validar rol antes de responder.

---

## HU-007. Resolver tenant activo
**Como** sistema  
**Quiero** resolver el tenant activo del usuario autenticado  
**Para** garantizar que toda la operación del dashboard quede aislada correctamente.

### Criterios de aceptación
- El tenant activo debe resolverse desde backend.
- El frontend no debe poder imponer arbitrariamente el tenant.
- Toda consulta privada debe ejecutarse con el tenant resuelto.
- Si no se puede resolver el tenant, el acceso debe bloquearse.

---

# Épica 3. Configuración por tenant

## HU-008. Configurar agentes por tenant
**Como** administrador de plataforma o configuración interna  
**Quiero** definir agentes asociados a un tenant  
**Para** que cada cliente opere con su propia configuración sin duplicar el backend.

### Criterios de aceptación
- Un agente debe poder asociarse a un tenant.
- Un tenant puede tener múltiples agentes.
- La configuración de agentes de un tenant no debe afectar a otro tenant.
- Las métricas del dashboard deben poder filtrar y agrupar por esos agentes.

---

## HU-009. Configurar reglas y flujos por tenant
**Como** administrador de plataforma o responsable de implementación  
**Quiero** parametrizar prompts, workflows y reglas por tenant  
**Para** adaptar la solución a cada negocio sin crear un backend distinto.

### Criterios de aceptación
- El sistema debe permitir asociar configuración específica a cada tenant.
- La configuración debe poder variar entre tenants sin afectar el core común.
- El backend compartido debe seguir siendo único.
- El diseño debe quedar preparado para evolucionar esa configuración en fases posteriores.

---

## HU-010. Mantener core compartido con personalización por tenant
**Como** negocio/plataforma  
**Quiero** que los clientes se soporten con un core compartido y configuración por tenant  
**Para** escalar el producto sin multiplicar el mantenimiento técnico.

### Criterios de aceptación
- La implementación de nuevos tenants no debe requerir un backend nuevo como patrón base.
- La personalización debe resolverse preferentemente por configuración.
- El sistema debe permitir extensiones por excepción cuando un caso lo requiera.
- El dashboard debe operar sobre un modelo de datos canónico compartido.

---

# Épica 4. Vista principal del dashboard

## HU-011. Ver KPIs principales
**Como** cliente  
**Quiero** ver los KPIs principales de mi operación  
**Para** entender rápidamente el desempeño de mis agentes y llamadas.

### Criterios de aceptación
- El dashboard debe mostrar al menos:
  - llamadas totales,
  - llamadas contestadas,
  - llamadas no contestadas,
  - tasa de contestación,
  - duración promedio,
  - duración total,
  - minutos facturados, si aplica,
  - llamadas en curso.
- Los KPIs deben corresponder al rango de fechas seleccionado.
- Los KPIs deben actualizarse al aplicar filtros.
- El sistema debe mostrar un estado vacío claro si no hay datos.

---

## HU-012. Ver tendencia de llamadas
**Como** cliente  
**Quiero** ver la tendencia de llamadas en el tiempo  
**Para** identificar comportamientos operativos y variaciones de volumen.

### Criterios de aceptación
- El dashboard debe mostrar una visualización temporal por día o periodo equivalente.
- La tendencia debe responder a los filtros activos.
- El gráfico no debe mostrar datos de otros tenants.
- Si no hay datos, el componente debe mantenerse visible con mensaje de ausencia de información.

---

## HU-013. Ver distribución por estado
**Como** cliente  
**Quiero** ver el porcentaje o distribución de llamadas por estado  
**Para** entender cuántas llamadas fueron contestadas, no contestadas o fallidas.

### Criterios de aceptación
- El dashboard debe mostrar distribución por estado normalizado.
- La distribución debe usar datos del tenant activo.
- Las categorías deben corresponder al catálogo definido de estados.
- El gráfico debe actualizarse con filtros.

---

## HU-014. Ver distribución por agente
**Como** cliente  
**Quiero** ver la distribución de llamadas por agente  
**Para** analizar carga operativa y desempeño por agente.

### Criterios de aceptación
- El sistema debe mostrar la distribución de llamadas por agente.
- Si existen llamadas sin agente, deben agruparse en una categoría controlada.
- La visualización debe responder a filtros activos.
- Los datos deben estar restringidos al tenant del usuario.

---

## HU-015. Ver heatmap de actividad
**Como** cliente  
**Quiero** ver el comportamiento de llamadas por día y hora  
**Para** identificar horas pico y patrones operativos.

### Criterios de aceptación
- El dashboard debe mostrar una visualización tipo heatmap o equivalente.
- La información debe agruparse según la zona horaria del cliente.
- El heatmap debe responder a filtros.
- La visualización debe usar únicamente datos persistidos del backend.

---

# Épica 5. Tabla de llamadas recientes

## HU-016. Ver tabla de llamadas recientes
**Como** cliente  
**Quiero** ver una tabla con mis llamadas recientes  
**Para** revisar rápidamente el detalle operativo más reciente.

### Criterios de aceptación
- La tabla debe mostrar como mínimo:
  - fecha,
  - hora,
  - duración,
  - nombre del agente,
  - resumen,
  - estado.
- La tabla debe ordenarse por fecha/hora descendente.
- La tabla debe respetar los filtros aplicados.
- La tabla debe mostrar solo llamadas del tenant del usuario.

---

## HU-017. Ver resumen de llamada
**Como** cliente  
**Quiero** ver un resumen de cada llamada cuando exista  
**Para** entender rápidamente el contenido de la interacción.

### Criterios de aceptación
- Si existe resumen, debe mostrarse en la tabla o en la vista correspondiente.
- Si no existe resumen, debe mostrarse un texto controlado como “Sin resumen” o equivalente.
- La falta de resumen no debe romper la tabla.
- El resumen solo debe ser visible para usuarios autorizados del tenant.

---

## HU-018. Navegar resultados paginados
**Como** cliente  
**Quiero** paginar o cargar más registros de llamadas  
**Para** revisar históricos sin saturar la interfaz.

### Criterios de aceptación
- La tabla debe soportar paginación o carga incremental.
- La paginación debe respetar filtros activos.
- El orden de los registros debe mantenerse consistente.
- El sistema debe devolver total o metadatos suficientes para navegar resultados.

---

# Épica 6. Filtros y segmentación

## HU-019. Filtrar por rango de fechas
**Como** cliente  
**Quiero** filtrar el dashboard por un rango de fechas  
**Para** analizar periodos específicos de operación.

### Criterios de aceptación
- El sistema debe permitir filtros rápidos:
  - hoy,
  - últimos 7 días,
  - últimos 30 días,
  - este mes,
  - rango personalizado.
- Todos los KPIs, gráficos y tablas deben actualizarse de manera consistente.
- Las fechas deben interpretarse con la zona horaria del cliente.
- El filtro debe afectar únicamente el tenant autorizado.

---

## HU-020. Filtrar por agente
**Como** cliente  
**Quiero** filtrar la información por agente  
**Para** analizar el desempeño individual o de un subconjunto de agentes.

### Criterios de aceptación
- El dashboard debe permitir seleccionar un agente.
- Todas las métricas y visualizaciones deben responder al filtro.
- Si el agente no pertenece al tenant, no debe devolver información.
- Debe existir opción para volver a “todos los agentes”.

---

## HU-021. Filtrar por estado de llamada
**Como** cliente  
**Quiero** filtrar por estado de llamada  
**Para** analizar casos contestados, no contestados, fallidos u otros.

### Criterios de aceptación
- El sistema debe permitir filtrar por estado normalizado.
- Los KPIs y tablas deben recalcularse con el estado seleccionado.
- El filtro debe ser compatible con rango de fechas y agente.
- No se deben mezclar estados originales del proveedor con estados internos del dashboard.

---

# Épica 7. Lógica de negocio de llamadas y métricas

## HU-022. Calcular llamadas contestadas
**Como** sistema  
**Quiero** clasificar correctamente las llamadas contestadas  
**Para** que las métricas del dashboard sean confiables.

### Criterios de aceptación
- El sistema debe usar la lógica interna definida para marcar una llamada como `answered`.
- La clasificación debe almacenarse como estado normalizado.
- El dashboard debe calcular métricas usando el estado normalizado.
- La clasificación debe ser consistente entre KPIs y tabla.

---

## HU-023. Calcular llamadas no contestadas
**Como** sistema  
**Quiero** clasificar correctamente las llamadas no contestadas  
**Para** reflejar con precisión el rendimiento operativo.

### Criterios de aceptación
- El sistema debe usar una lógica normalizada para `unanswered`.
- Las llamadas en curso no deben contarse como no contestadas.
- Las llamadas no contestadas deben participar en las métricas correspondientes.
- La clasificación debe ser visible en tabla y gráficos.

---

## HU-024. Calcular duración promedio
**Como** cliente  
**Quiero** ver la duración promedio de llamadas contestadas  
**Para** entender la calidad y extensión de las interacciones.

### Criterios de aceptación
- La duración promedio debe calcularse sobre llamadas contestadas.
- El cálculo debe respetar filtros activos.
- El valor debe venir del backend.
- El sistema debe mostrar un estado vacío si no hay llamadas elegibles.

---

## HU-025. Ver minutos facturados
**Como** cliente  
**Quiero** ver minutos facturados o consumidos  
**Para** tener referencia operativa y futura trazabilidad de costos.

### Criterios de aceptación
- El sistema debe mostrar minutos facturados si el dato existe.
- El dato debe provenir de la base interna sincronizada.
- El sistema debe poder coexistir con duración real y minutos facturados.
- Si no existe dato facturado, el sistema debe manejar la ausencia de forma controlada.

---

# Épica 8. Ingesta, persistencia y normalización desde Ultravox

## HU-026. Persistir llamadas desde eventos externos
**Como** sistema  
**Quiero** almacenar internamente las llamadas recibidas desde Ultravox  
**Para** construir métricas confiables sin depender del proveedor en tiempo de consulta.

### Criterios de aceptación
- El backend debe recibir eventos o datos de llamadas desde Ultravox.
- El backend debe persistir la llamada en la base interna.
- Cada llamada debe quedar asociada a un tenant.
- El dashboard debe leer desde la base interna y no desde Ultravox directamente.

---

## HU-027. Normalizar estado de llamada
**Como** sistema  
**Quiero** conservar estado original y estado normalizado  
**Para** separar trazabilidad técnica de la lógica analítica del dashboard.

### Criterios de aceptación
- La llamada debe poder almacenar `provider_status` y `normalized_status`.
- El dashboard debe usar solo `normalized_status`.
- La trazabilidad técnica debe mantenerse disponible para auditoría.
- El proceso de normalización debe ser consistente y reutilizable.

---

## HU-028. Reconciliar datos faltantes
**Como** sistema  
**Quiero** reconciliar llamadas y eventos faltantes  
**Para** recuperar consistencia si se pierde información en tiempo real.

### Criterios de aceptación
- El backend debe soportar jobs de reconciliación o backfill.
- Una llamada incompleta debe poder actualizarse después.
- El dashboard debe mostrar la mejor información disponible sin romperse.
- La plataforma debe registrar `last_synced_at` o equivalente.

---

## HU-029. Asociar llamadas a agente y tenant
**Como** sistema  
**Quiero** asociar cada llamada al tenant y al agente correspondiente cuando sea posible  
**Para** que las métricas del dashboard sean útiles y seguras.

### Criterios de aceptación
- Toda llamada persistida debe tener `tenant_id`.
- Cuando exista información suficiente, la llamada debe asociarse a un agente.
- Si no hay agente, la llamada debe quedar como no asignada sin romper métricas.
- El dashboard debe poder agrupar por agente y también incluir no asignadas.

---

# Épica 9. Seguridad funcional y autorización

## HU-030. Proteger endpoints del dashboard
**Como** sistema  
**Quiero** proteger todos los endpoints privados del dashboard  
**Para** evitar acceso no autorizado a métricas y llamadas.

### Criterios de aceptación
- Todo endpoint privado debe validar autenticación.
- Todo endpoint debe resolver usuario interno.
- Todo endpoint debe resolver tenant activo.
- Todo endpoint debe validar rol.
- Si falla alguno de esos pasos, la respuesta debe ser de acceso denegado.

---

## HU-031. Restringir acceso por tenant
**Como** sistema  
**Quiero** imponer el tenant desde backend  
**Para** evitar fugas de información por manipulación de parámetros.

### Criterios de aceptación
- El backend no debe confiar en `tenant_id` enviado por frontend.
- El tenant debe resolverse desde el contexto autenticado.
- Toda query debe filtrar por el tenant autorizado.
- Un usuario cliente no puede elevar privilegios cambiando parámetros de request.

---

## HU-032. Auditar accesos y consultas
**Como** administrador de plataforma  
**Quiero** que los accesos relevantes queden auditados  
**Para** tener trazabilidad operativa y de seguridad.

### Criterios de aceptación
- El sistema debe registrar eventos de acceso relevantes.
- Debe poder saberse qué usuario consultó qué tenant y cuándo.
- Los accesos administrativos cruzados deben quedar trazables.
- La auditoría debe almacenarse en la base interna.

---

# Épica 10. Estados vacíos, errores y experiencia de uso

## HU-033. Ver estados vacíos útiles
**Como** cliente  
**Quiero** ver mensajes claros cuando no existan datos  
**Para** entender que el dashboard funciona aunque no haya actividad.

### Criterios de aceptación
- Si no existen llamadas en el periodo filtrado, el dashboard debe mostrar un estado vacío claro.
- Los gráficos deben mantener su estructura visual aunque no haya datos.
- La tabla debe indicar ausencia de registros de forma controlada.
- El estado vacío no debe parecer error del sistema.

---

## HU-034. Manejo de error de carga
**Como** cliente  
**Quiero** recibir mensajes claros si falla la carga del dashboard  
**Para** saber que ocurrió un problema y poder reintentar.

### Criterios de aceptación
- Si falla la consulta de un módulo del dashboard, se debe mostrar mensaje controlado.
- Debe existir opción de reintento.
- El error no debe exponer detalles sensibles del backend.
- La interfaz debe degradarse de forma elegante.

---

# Épica 11. Evolución futura y extensibilidad

## HU-035. Dejar base lista para reportes futuros
**Como** negocio  
**Quiero** que la Fase II quede preparada para futuras ampliaciones  
**Para** evolucionar hacia exportaciones, comparativos y analítica avanzada sin rediseñar desde cero.

### Criterios de aceptación
- El modelo de datos debe soportar crecimiento hacia exportaciones y snapshots.
- La arquitectura debe permitir nuevas métricas sin romper las existentes.
- El modelo debe soportar múltiples tenants y múltiples agentes por tenant.
- La solución debe quedar desacoplada tanto del proveedor de identidad como del proveedor de llamadas.

---

## HU-036. Soportar extensiones por excepción
**Como** plataforma  
**Quiero** permitir casos especiales de integración o lógica avanzada  
**Para** atender clientes complejos sin romper el core compartido.

### Criterios de aceptación
- El diseño debe permitir servicios o adaptadores específicos cuando un cliente lo requiera.
- Esa extensión no debe convertirse en una duplicación completa del backend como modelo general.
- El core del producto debe seguir siendo compartido.
- Las métricas del dashboard deben seguir saliendo del backend interno de la plataforma.
