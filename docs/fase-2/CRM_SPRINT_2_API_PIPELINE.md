# Sprint CRM 2 — API Pipeline

## Objetivo

Fortalecer la API CRM multitenant con endpoints avanzados de pipeline, filtros, métricas, tareas y notas internas, preparando el backend para que Sprint CRM 3 pueda construir la UI CRM tipo pipeline/Kanban sin rediseñar backend.

---

## Rama

- **Rama creada:** `feature/crm-sprint-2-api-pipeline`
- **Rama base:** `feature/crm-sprint-1-ultravox-ingestion`
- **Razón:** Sprint CRM 1 no fue mergeado a `develop` al momento de iniciar Sprint 2. La base CRM (modelos, migración, servicios de ingesta) está únicamente en la rama Sprint 1.

---

## Endpoints creados o ampliados

| Método | Path | Propósito |
|--------|------|-----------|
| `GET` | `/api/v1/crm/pipeline` | Pipeline stages (existente, ampliado) |
| `GET` | `/api/v1/crm/summary` | Resumen CRM (existente) |
| `GET` | `/api/v1/crm/leads` | Listado avanzado con filtros |
| `GET` | `/api/v1/crm/leads/{lead_id}` | Detalle completo con actividades y tareas |
| `PATCH` | `/api/v1/crm/leads/{lead_id}` | Actualización manual de lead |
| `PATCH` | `/api/v1/crm/leads/{lead_id}/stage` | Cambio manual de etapa |
| `GET` | `/api/v1/crm/pipeline/board` | Pipeline agrupado por columnas (Kanban) |
| `GET` | `/api/v1/crm/activities` | Actividades filtrables |
| `POST` | `/api/v1/crm/leads/{lead_id}/notes` | Notas internas |
| `GET` | `/api/v1/crm/tasks` | Listar tareas |
| `POST` | `/api/v1/crm/tasks` | Crear tarea |
| `PATCH` | `/api/v1/crm/tasks/{task_id}` | Actualizar tarea |
| `DELETE` | `/api/v1/crm/tasks/{task_id}` | Eliminar tarea |
| `GET` | `/api/v1/crm/metrics` | Métricas CRM |

---

## Contratos request/response

### GET /api/v1/crm/leads

**Query params:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `page` | int | 1 | Número de página |
| `page_size` | int | 20 | Items por página (max 100) |
| `stage_key` | string | - | Filtrar por etapa |
| `status` | string | - | open, won, lost, unqualified, paused |
| `search` | string | - | Búsqueda en nombre, teléfono, email, empresa, resumen, interés, caso de uso |
| `source` | string | - | Filtrar por fuente |
| `campaign` | string | - | Filtrar por campaña |
| `assigned_agent_id` | string | - | Filtrar por agente asignado |
| `date_from` | datetime | - | Fecha de creación desde |
| `date_to` | datetime | - | Fecha de creación hasta |
| `has_phone` | bool | - | Con teléfono |
| `has_email` | bool | - | Con email |
| `sort_by` | string | updated_at | created_at, updated_at, last_activity_at, stage, contact_name |
| `sort_order` | string | desc | asc, desc |

**Response:**
```json
{
  "items": [{
    "lead_id": "uuid",
    "contact_name": "string",
    "contact_phone": "string|null",
    "contact_email": "string|null",
    "company": "string|null",
    "stage_key": "string",
    "stage_name": "string",
    "status": "string",
    "interest": "string|null",
    "use_case": "string|null",
    "source": "string|null",
    "campaign": "string|null",
    "short_summary": "string|null",
    "last_activity_at": "datetime|null",
    "last_call_id": "string|null",
    "created_at": "datetime",
    "updated_at": "datetime"
  }],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "total_pages": 1,
  "filters_applied": {}
}
```

### PATCH /api/v1/crm/leads/{lead_id}

**Body:**
```json
{
  "interest": "Alto",
  "industry": "Real Estate",
  "use_case": "Ventas",
  "volume": "100",
  "pain_point": "Falta de seguimiento",
  "budget_range": "$500-$1000",
  "intent_level": "high",
  "next_action": "Llamar viernes",
  "lead_score": 85,
  "status": "open",
  "source": "webhook",
  "campaign": "campana-junio"
}
```

**Validaciones:** `lead_score` entre 0-100, `status` en [open, won, lost, unqualified, paused].

### PATCH /api/v1/crm/leads/{lead_id}/stage

**Body:**
```json
{
  "stage_key": "qualified",
  "reason": "Cliente solicitó propuesta"
}
```

### GET /api/v1/crm/pipeline/board

**Query params:** `limit_per_stage` (default 20), `search`, `status`, `source`, `campaign`, `assigned_agent_id`

**Response:**
```json
{
  "stages": [{
    "id": "uuid",
    "key": "connected",
    "name": "Conversación establecida",
    "position": 3,
    "count": 12,
    "leads": [{
      "id": "uuid",
      "contact_name": "string",
      "phone": "string|null",
      "company": "string|null",
      "short_summary": "string|null",
      "last_activity_at": "datetime|null",
      "status": "open"
    }]
  }]
}
```

### POST /api/v1/crm/tasks

**Body:**
```json
{
  "lead_id": "uuid|null",
  "contact_id": "uuid|null",
  "title": "Llamar al cliente",
  "description": "Recordatorio de llamada",
  "due_at": "2026-07-01T00:00:00Z|null",
  "priority": "high",
  "assigned_to_user_id": "uuid|null"
}
```

### POST /api/v1/crm/leads/{lead_id}/notes

**Body:**
```json
{
  "note": "Cliente pidió seguimiento el viernes."
}
```

### GET /api/v1/crm/metrics

**Query params:** `date_from`, `date_to`, `source`, `campaign`, `assigned_agent_id`

**Response:**
```json
{
  "total_contacts": 50,
  "total_leads": 40,
  "open_leads": 25,
  "won_leads": 5,
  "lost_leads": 8,
  "unqualified_leads": 2,
  "leads_by_stage": [{"stage_key": "new", "stage_name": "Nuevo", "count": 10}],
  "leads_by_source": [{"source": "webhook", "count": 30}],
  "leads_by_campaign": [{"campaign": "junio", "count": 15}],
  "leads_created_today": 3,
  "leads_created_this_week": 12,
  "leads_created_this_month": 40,
  "scheduled_leads": 4,
  "voicemail_leads": 6,
  "follow_up_leads": 8,
  "pending_tasks": 10,
  "overdue_tasks": 3,
  "conversion_rate": 12.5,
  "contact_completion_rate": 75.0
}
```

---

## Filtros disponibles

| Endpoint | Filtros |
|----------|---------|
| `/leads` | page, page_size, stage_key, status, search, source, campaign, assigned_agent_id, date_from, date_to, has_phone, has_email, sort_by, sort_order |
| `/activities` | lead_id, contact_id, activity_type, date_from, date_to, limit, page |
| `/pipeline/board` | limit_per_stage, search, status, source, campaign, assigned_agent_id |
| `/tasks` | lead_id, contact_id, status, priority |
| `/metrics` | date_from, date_to, source, campaign, assigned_agent_id |

---

## Reglas de multitenancy

- Todos los endpoints usan `AuthContext` y `context.tenant.id`
- Usuario tenant solo ve datos de su tenant
- No se acepta `tenant_id` desde frontend tenant
- `lead_id`, `contact_id` y `task_id` se validan por tenant
- Si el recurso pertenece a otro tenant: **404**, no 403

---

## Reglas de cambio manual de etapa

- `stage_key` debe existir para el tenant (vía `CrmPipelineService.get_stage_by_key`)
- `deduplication_key` = `manual:{from_stage_id}:{to_stage_id}:{timestamp}` (permite múltiples cambios manuales)
- Si etapa destino es terminal:
  - `won` → `status = won`
  - `lost` o `not_interested` → `status = lost`
- No se reabre automáticamente un lead perdido/ganado al moverlo a etapa no terminal
- Se crea actividad `stage_changed`

---

## Reglas de notas

- `POST /leads/{lead_id}/notes`
- Crea actividad `activity_type = note`, `title = "Nota interna"`, `description = texto`
- Valida tenant
- No permite nota vacía (422)
- No expone `payload_json`

---

## Reglas de tareas

- `status` permitido: pending, done, cancelled, overdue
- `priority` permitido: low, medium, high
- `lead_id` y `contact_id` deben pertenecer al tenant
- `assigned_to_user_id` debe ser miembro activo del tenant
- `POST task` crea actividad `task_created`
- `PATCH task` crea actividad `task_updated`
- Si `status` cambia a `done`, crea actividad `task_completed`
- `DELETE task` es hard delete

---

## Métricas CRM

- `conversion_rate = won_leads / total_leads * 100`
- `contact_completion_rate = contactos con phone o email / total_contacts * 100`
- leads_by_stage, leads_by_source, leads_by_campaign
- leads_created_today, leads_created_this_week, leads_created_this_month
- scheduled_leads, voicemail_leads, follow_up_leads (por stage)
- pending_tasks, overdue_tasks

---

## Ejemplos curl

```bash
# Listar leads con filtros
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.serviglobal-ia.com/api/v1/crm/leads?page=1&page_size=20&stage_key=qualified&search=Carlos"

# Detalle de lead
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.serviglobal-ia.com/api/v1/crm/leads/{lead_id}"

# Actualizar lead
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"interest": "Alto", "lead_score": 80}' \
  "https://api.serviglobal-ia.com/api/v1/crm/leads/{lead_id}"

# Cambiar etapa
curl -X PATCH -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"stage_key": "qualified", "reason": "Cliente interesado"}' \
  "https://api.serviglobal-ia.com/api/v1/crm/leads/{lead_id}/stage"

# Pipeline board
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.serviglobal-ia.com/api/v1/crm/pipeline/board?limit_per_stage=20"

# Crear tarea
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"lead_id": "uuid", "title": "Llamar", "priority": "high"}' \
  "https://api.serviglobal-ia.com/api/v1/crm/tasks"

# Crear nota
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"note": "Cliente pidió seguimiento"}' \
  "https://api.serviglobal-ia.com/api/v1/crm/leads/{lead_id}/notes"

# Obtener métricas
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.serviglobal-ia.com/api/v1/crm/metrics"
```

---

## Schemas creados o modificados

Archivo: `backend/app/schemas/crm.py`

- `PipelineStageSchema` — etapa del pipeline
- `ContactBriefSchema` — contacto resumido
- `LeadStageCount` — conteo por etapa
- `LeadListItem` — item de listado avanzado
- `LeadBriefSchema` — lead resumido (compatibilidad Sprint 1)
- `LeadsListResponse` — respuesta paginada con filtros aplicados
- `ActivitySchema` — actividad sanitizada (sin payload_json)
- `TaskResponse` — respuesta tarea
- `TaskCreateRequest` — crear tarea
- `TaskUpdateRequest` — actualizar tarea
- `LeadUpdateRequest` — actualizar lead
- `StageUpdateRequest` — cambiar etapa
- `NoteCreateRequest` — crear nota
- `LeadDetailResponse` — detalle completo con actividades y tareas
- `CrmSummaryResponse` — resumen CRM
- `PipelineBoardLeadItem` — item de pipeline board
- `PipelineStageLeads` — etapa con leads en board
- `PipelineBoardResponse` — respuesta board completo
- `LeadsByStageMetric`, `LeadsBySourceMetric`, `LeadsByCampaignMetric` — métricas agrupadas
- `CrmMetricsResponse` — respuesta métricas completa

---

## Servicios creados o modificados

| Servicio | Archivo | Propósito |
|----------|---------|-----------|
| `CrmLeadService` | `crm_lead_service.py` | Ampliado: update_lead, change_stage, add_note, get_lead_by_id |
| `CrmActivityService` | `crm_activity_service.py` | **Nuevo**: crear actividad, listar con filtros |
| `CrmTaskService` | `crm_task_service.py` | **Nuevo**: CRUD completo de tareas con validaciones multitenant |
| `CrmMetricsService` | `crm_metrics_service.py` | **Nuevo**: cálculo de métricas agregadas |
| `CrmQueryService` | `crm_query_service.py` | **Nuevo**: listado avanzado de leads con filtros y pipeline board |

---

## Tests

Archivo: `backend/test_crm_sprint_2.py`

28 tests creados:

- **Listado y filtros (5):** filter_by_stage, search_by_contact_name, search_by_phone, pagination, sorting_allowed_fields
- **Detalle (2):** includes_activities_and_tasks, cross_tenant_returns_404
- **Actualización lead (3):** allowed_fields, rejects_invalid_score, creates_activity
- **Cambio de etapa (3):** manual_stage_change, creates_stage_history, cross_tenant_404
- **Pipeline board (2):** groups_leads_by_stage, respects_limit_per_stage
- **Actividades (2):** filter_by_type, do_not_expose_payload_json
- **Notas (2):** create_note, empty_note_rejected
- **Tareas (5):** create_task, update_status_done, cross_tenant_404, assignee_must_belong_to_tenant, delete_task
- **Métricas (4):** counts, conversion_rate, contact_completion_rate, filters_by_date

---

## Limitaciones conocidas

1. **Hard delete en tareas:** `DELETE /tasks/{id}` elimina físicamente el registro. No hay borrado lógico.
2. **Pipeline board sin WebSockets:** No hay actualización en tiempo real. Sprint CRM 3 debe implementar polling o WebSockets.
3. **Sin scoring LLM:** `lead_score` es manual. No hay clasificación automática por IA.
4. **Sin drag & drop backend:** El endpoint `pipeline/board` solo devuelve datos agrupados. El drag & drop se implementa en frontend.
5. **Paginación en activities:** Usa offset simple (page * limit). Para grandes volúmenes, considerar cursor-based.
6. **`HTTP_422_UNPROCESSABLE_ENTITY` deprecado:** FastAPI 0.115+ usa `HTTP_422_UNPROCESSABLE_CONTENT`. Se usó `HTTP_422_UNPROCESSABLE_ENTITY` para compatibilidad. Actualizar en próxima revisión.

---

## Alcance del Sprint CRM 3

- UI pipeline/Kanban con drag & drop
- Integración del pipeline board endpoint
- Formularios de creación y edición de leads, tareas y notas
- Panel de métricas CRM
- Actualizaciones en tiempo real (WebSockets o polling)
- Posible integración de scoring LLM para lead scoring automático

---

## Tests ejecutados y resultado

```
Ran 100 tests in 13.796s
OK
```

Desglose:
- `test_crm_sprint_1.py` — 18 tests ✅
- `test_crm_sprint_2.py` — 28 tests ✅
- `test_sprint1_auth_context.py` — 9 tests ✅
- `test_sprint3_ultravox_ingestion.py` — 13 tests ✅
- `test_sprint4b_dashboard_api.py` — 7 tests ✅
- `test_sprint7a_onboarding.py` — 25 tests ✅