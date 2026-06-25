# CRM Sprint 5: Dashboard comercial y métricas CRM

## 1. Objetivo del sprint
El objetivo de este sprint es implementar el **Dashboard comercial y métricas CRM** para el arrendamiento comercial y embudo de ventas multitenant. El sistema ayuda a responder preguntas comerciales críticas sobre la eficiencia del funnel y la necesidad de intervención humana en la gestión de leads sin requerir IA en este sprint.

---

## 2. Endpoint creado
**GET** `/api/v1/crm/dashboard`

### Filtros y Parámetros Disponibles:
- `range`: Períodos preconfigurados (`today` | `7d` | `30d` | `month` | `custom`). Si no se provee, se asume `30d`.
- `date_from` (YYYY-MM-DD): Requerido únicamente si `range=custom`.
- `date_to` (YYYY-MM-DD): Requerido únicamente si `range=custom`.
- `source`: Filtra por canal de procedencia del lead (ej. `landing`, `facebook`).
- `campaign`: Filtra por campaña UTM (ej. `demo-crm`).

---

## 3. Estructura de Respuesta del Endpoint
El JSON de respuesta está definido bajo la siguiente estructura:

```json
{
  "period": {
    "from": "2026-06-01",
    "to": "2026-06-30",
    "range": "30d"
  },
  "kpis": {
    "total_leads": 0,
    "new_leads": 0,
    "contacted_leads": 0,
    "connected_leads": 0,
    "qualified_leads": 0,
    "scheduled_leads": 0,
    "follow_up_leads": 0,
    "not_interested_leads": 0,
    "won_leads": 0,
    "lost_leads": 0,
    "open_leads": 0,
    "pending_tasks": 0,
    "overdue_tasks": 0,
    "leads_with_next_action": 0
  },
  "conversion": {
    "contact_rate": 0.0,
    "connection_rate": 0.0,
    "qualification_rate": 0.0,
    "schedule_rate": 0.0,
    "win_rate": 0.0
  },
  "funnel": [
    { "stage": "new", "label": "Nuevo", "count": 0 },
    { "stage": "contacted", "label": "Contactado", "count": 0 },
    { "stage": "connected", "label": "Conectado", "count": 0 },
    { "stage": "qualified", "label": "Calificado", "count": 0 },
    { "stage": "scheduled", "label": "Agendado", "count": 0 },
    { "stage": "won", "label": "Ganado", "count": 0 }
  ],
  "sources": [
    {
      "source": "landing",
      "total_leads": 0,
      "qualified_leads": 0,
      "scheduled_leads": 0,
      "won_leads": 0,
      "conversion_rate": 0.0
    }
  ],
  "campaigns": [
    {
      "campaign": "demo-crm",
      "total_leads": 0,
      "qualified_leads": 0,
      "scheduled_leads": 0,
      "won_leads": 0,
      "conversion_rate": 0.0
    }
  ],
  "calls": {
    "total_calls": 0,
    "answered_calls": 0,
    "unanswered_calls": 0,
    "voicemail_calls": 0,
    "failed_calls": 0,
    "average_duration_seconds": 0.0,
    "total_billed_minutes": 0.0
  },
  "pending_actions": [
    {
      "lead_id": "uuid",
      "contact_name": "Nombre",
      "stage": "follow_up",
      "next_action": "confirm_booking",
      "source": "landing",
      "campaign": "demo-crm",
      "updated_at": "2026-06-01T10:00:00Z"
    }
  ]
}
```

---

## 4. Métricas Calculadas e Interpretación de Negocio

### KPIs generales:
- `total_leads`: Cantidad total de leads que encajan en el filtro.
- `new_leads`, `contacted_leads`, `connected_leads`, `qualified_leads`, `scheduled_leads`, `follow_up_leads`, `not_interested_leads`, `won_leads`, `lost_leads`: Conteo de leads que están actualmente en esa respectiva etapa.
- `open_leads`: Leads con estado `"open"`.
- `pending_tasks` y `overdue_tasks`: Conteo de tareas comerciales pendientes y vencidas asociadas al tenant.
- `leads_with_next_action`: Conteo de leads con campo `next_action` relleno.

### Reglas de Conversión (Embudo Acumulativo):
Para representar un embudo real y evitar tasas incongruentes, se computan los numeradores y denominadores de forma acumulativa:
- `contact_rate` (Tasa de Contacto): Leads que iniciaron llamada o superior (`contacted`, `connected`, `qualified`, `scheduled`, `won`, `follow_up`, `not_interested`, `lost`) / `total_leads`
- `connection_rate` (Tasa de Conexión): Leads que conectaron llamada o superior (`connected`, `qualified`, `scheduled`, `won`, `follow_up`, `not_interested`, `lost`) / `contacted_cum`
- `qualification_rate` (Tasa de Calificación): Leads calificados o superior (`qualified`, `scheduled`, `won`) / `connected_cum`
- `schedule_rate` (Tasa de Agendamiento): Leads agendados o superior (`scheduled`, `won`) / `qualified_cum`
- `win_rate` (Tasa de Cierre): Leads ganados (`won`) / `scheduled_cum`

*Si algún denominador es igual a 0, la tasa correspondiente retorna automáticamente 0.0.*

### Reglas de Acciones Pendientes (Acción humana requerida):
Se listan los leads que cumplan con al menos una de las siguientes condiciones:
1. `next_action` no está vacío ni nulo.
2. Etapa actual es `follow_up`.
3. Etapa actual es `contacted` y no tiene `last_call_id` registrado como conectado (`answered`).
4. Tienen tareas comerciales pendientes o vencidas asociadas.

El listado está limitado a los últimos 20 registros modificados (`updated_at` desc).

---

## 5. Componentes Frontend Creados
Se ha centralizado la vista del panel en:
- `frontend/app/[locale]/crm/dashboard/page.tsx` (Server Component)
- `frontend/app/[locale]/crm/dashboard/crm-dashboard-view-client.tsx` (Client component)
  - **Filtros Dinámicos**: Selector de rango de fechas con soporte para rango personalizado e inputs de fuentes y campañas.
  - **KPI Grid**: 4 tarjetas principales de KPIs comerciales.
  - **Embudo Comercial (CSS puro)**: Renderizado del embudo con anchos de barra porcentuales y gradientes vibrantes.
  - **Métricas de Conversión**: 5 tarjetas con la eficiencia porcentual de cada paso del funnel.
  - **Rendimiento por Fuente / Campaña**: Tablas con estadísticas de conversión para cada origen y campaña.
  - **Cruce de Métricas de Llamadas**: Resumen del desempeño telefónico de los agentes de voz IA (llamadas atendidas, no contestadas, buzones, duración promedio y costos de facturación).
  - **Acciones Pendientes**: Listado con enlaces directos a la página de detalle del lead (`/[locale]/crm/leads/[leadId]`) para rápida intervención comercial.

Además, se actualizó:
- `frontend/components/crm/CrmHeader.tsx` para agregar la opción **Dashboard Comercial** al inicio de las pestañas de navegación.

---

## 6. Tests Ejecutados

### Backend Unit Tests:
Se crearon los tests de integración en `backend/test_crm_dashboard_metrics.py` cubriendo:
- `test_dashboard_empty_state_returns_zero`
- `test_dashboard_kpis_total_leads`
- `test_dashboard_counts_by_stage`
- `test_dashboard_conversion_rates`
- `test_dashboard_filters_by_date_range`
- `test_dashboard_filters_by_source`
- `test_dashboard_filters_by_campaign`
- `test_dashboard_pending_actions`
- `test_dashboard_does_not_cross_tenant_data`
- `test_dashboard_call_metrics`
- `test_dashboard_denominator_zero_returns_zero`

Todos los tests del backend pasaron de forma exitosa (11/11 tests OK).
Las pruebas de compilación total del backend también fueron exitosas.

### Frontend Validations:
- Typechecking de TypeScript completado sin errores (`npx tsc --noEmit`).
- Análisis de calidad y formato de ESLint completado sin errores ni advertencias (`npm run lint`).
- Generación de build de producción de Next.js completado sin errores (`npm run build`).

---

## 7. Limitaciones y Próximos Pasos
- **Rango de fecha personalizado**: La interfaz del frontend tiene campos nativos de fecha que son enviados en formato `YYYY-MM-DD` al backend, donde se interpretan según la zona horaria del tenant.
- **Acciones en tiempo real**: Se decidió no usar WebSockets ni actualizaciones automáticas en tiempo real en este sprint conforme al alcance delimitado. Se recomienda un botón manual de refresco si se requiere forzar recarga (el filtrado por defecto refresca la información del servidor).
