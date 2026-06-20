# Sprint CRM 1: Ingesta de Webhooks Ultravox y Base CRM

## 1. Objetivo del Sprint
El objetivo del **Sprint CRM 1** es construir los cimientos del backend para el módulo de CRM multitenant de ServiGlobal IA, procesando eventos webhooks de Ultravox (`call.joined`, `call.ended` y `call.billed`) para realizar de forma automática e idempotente:
- Inicialización perezosa (lazy) de pipelines y etapas comerciales por tenant.
- Resolución o creación de contactos, normalizando teléfonos (con soporte para prefijos de Colombia).
- Creación y asociación de leads comerciales abiertos a partir de llamadas.
- Clasificación determinista de la etapa comercial según el resultado de la llamada y los resúmenes generados por IA.
- Registro histórico de actividades de CRM (`call_started`, `call_joined`, `call_ended`, `call_billed`, `stage_changed`) guardando trazabilidad de transiciones de etapas.
- Exposición de APIs REST mínimas para validación, garantizando la seguridad multitenant.

---

## 2. Modelo de Datos CRM y Tablas Creadas
Se han diseñado e implementado las siguientes tablas en el esquema de la base de datos:

### `crm_contacts` (Contactos)
Representa a las personas / clientes dentro de un tenant.
- **Deduplicación:** Se prioriza la clave única `tenant_id` + `phone_normalized` (teléfono limpio y normalizado). Si no hay teléfono, se deduplica por `tenant_id` + `email`.
- **Campos principales:** `id`, `tenant_id`, `name`, `phone`, `phone_normalized`, `email`, `company`, `source`, `first_seen_at`, `last_seen_at`, `status`, `metadata_json`, `created_at`, `updated_at`.

### `crm_pipeline_stages` (Etapas de Venta)
Representa las fases del embudo de ventas por tenant.
- **Etapas por defecto:** `new` (Nuevo), `contacted` (Contactado), `connected` (Conversación establecida), `qualified` (Calificado), `scheduled` (Cita agendada), `follow_up` (Requiere seguimiento), `voicemail` (Buzón de voz), `not_interested` (No interesado), `won` (Convertido), `lost` (Perdido).
- **Campos principales:** `id`, `tenant_id`, `key`, `name`, `position`, `is_default`, `is_terminal`.

### `crm_leads` (Oportunidades de Negocio)
Representa oportunidades comerciales abiertas para un contacto.
- **Regla MVP:** Un contacto puede tener un solo lead abierto al mismo tiempo; si ya existe, se reutiliza y actualizan sus datos en lugar de duplicar oportunidades.
- **Campos principales:** `id`, `tenant_id`, `contact_id`, `current_stage_id`, `status` (open, won, lost, unqualified, paused), `lead_score`, `interest`, `use_case`, `pain_point`, `last_call_id`, `summary`, `short_summary`.

### `crm_activities` (Historial de Interacciones)
Historial cronológico de eventos asociados a un lead/contacto, registrando transiciones de etapas.
- **Idempotencia:** Evita duplicados mediante un constraint unique sobre `(tenant_id, call_id, activity_type, deduplication_key)`.
- **Campos principales:** `id`, `tenant_id`, `lead_id`, `contact_id`, `call_id`, `activity_type`, `title`, `description`, `outcome`, `occurred_at`, `payload_json`, `from_stage_id`, `to_stage_id`, `deduplication_key`, `created_at`.

### `crm_tasks` (Tareas de Seguimiento)
Estructura básica para agendamiento de tareas por lead.
- **Campos principales:** `id`, `tenant_id`, `lead_id`, `contact_id`, `assigned_to_user_id`, `title`, `description`, `due_at`, `status` (pending, done), `priority`.

---

## 3. Eventos Ultravox Procesados y Reglas de Extracción de Payload
La extracción se realiza de manera defensiva a partir de las fuentes `call.metadata`, `call.initialState`, `call.requestContext` y los campos del propio objeto `call`.

- **Teléfono (Orden de prioridad):**
  1. `call.metadata.user_phone`
  2. `call.initialState.phone`
  3. `call.initialState.user_phone`
  4. `call.customerPhone`
  5. `call.phone`
  6. `call.sipDetails.from`
- **Nombre (Orden de prioridad):**
  1. `call.metadata.user_name`
  2. `call.initialState.name`
  3. `call.initialState.user_name`
  4. Fallback: `"Lead sin nombre"`
- **Email (Orden de prioridad):**
  1. `call.metadata.user_email`
  2. `call.initialState.email`
  3. `call.initialState.user_email`

---

## 4. Reglas de Deduplicación e Idempotencia
- **Contactos:** Únicos por `tenant_id` + `phone_normalized`. Si el número telefónico ya existe dentro del mismo tenant, se reutiliza el contacto y se actualiza su campo `last_seen_at` y metadatos. Si no hay teléfono, se aplica la misma lógica usando el email.
- **Leads:** Se busca el lead abierto más reciente para el contacto (`status == "open"`). Si existe, se vincula y actualizan; de lo contrario, se crea uno nuevo. Esto evita múltiples leads duplicados por la misma llamada.
- **Actividades:** Idempotencia estricta usando `UniqueConstraint` en `(tenant_id, call_id, activity_type, deduplication_key)`. Para los eventos `stage_changed`, la `deduplication_key` se establece con la clave de la etapa de destino (ej. `connected`, `scheduled`), garantizando que se almacene el historial real de cambios de etapa por llamada sin que se sobrescriban entre sí.

---

## 5. Reglas de Pipeline y Clasificación Comercial Determinista
La lógica de negocio implementa la clasificación de leads sin depender de llamadas externas a LLMs en este sprint:
1. Si la llamada resulta en **voicemail** (contestador/buzón) ➔ etapa `voicemail`, `next_action = "follow_up"`.
2. Si la llamada es **unanswered** (no contestada/ocupada) ➔ etapa `follow_up`.
3. Si el resumen de la llamada contiene intenciones de **cita agendada** (ej. `"agend"`, `"cita"`, `"reun"`) ➔ etapa `scheduled`.
4. Si contiene intenciones de **rechazo / no interesado** (ej. `"no quiere"`, `"not interest"`) ➔ etapa `not_interested` (el estado del lead pasa a `lost`).
5. Si contiene intenciones de **calificación / interés** (ej. `"interes"`, `"cotiz"`, `"propuest"`) ➔ etapa `qualified`.
6. Si no hay señales claras ➔ se mantiene la etapa actual.

---

## 6. Endpoints Creados para Validación (Multitenant)
Se habilitan los siguientes endpoints de lectura protegidos por Auth0 multitenant. Ninguno expone el payload crudo (`payload_json`):
- `GET /api/v1/crm/pipeline` ➔ Lista de etapas configuradas por tenant.
- `GET /api/v1/crm/summary` ➔ Resumen cuantitativo de leads y contactos del tenant.
- `GET /api/v1/crm/leads` ➔ Oportunidades comerciales paginadas del tenant.
- `GET /api/v1/crm/leads/{lead_id}` ➔ Detalle de una oportunidad, incluyendo su contacto e historial de actividades sanitizado.
- `GET /api/v1/crm/activities` ➔ Historial de actividades recientes del tenant sin campos internos expuestos.

---

## 7. Cómo Probar con Payloads Ultravox

### A. Prueba de `call.joined` (Establecimiento de Llamada)
Envía este payload para simular que el cliente se ha conectado. Se creará automáticamente un contacto normalizado (con prefijo +57), un lead abierto, y las actividades correspondientes.

```json
{
  "event": "call.joined",
  "eventId": "evt-joined-001",
  "call": {
    "callId": "call-joined-test-123",
    "customerPhone": "3112223344",
    "metadata": {
      "tenant_id": "TU_TENANT_ID",
      "user_name": "Carlos Gomez",
      "interest": "Agentes de Voz AI"
    }
  }
}
```

### B. Prueba de `call.ended` (Fin de Llamada y Clasificación)
Envía este payload para simular el fin de la llamada con la clasificación correspondiente (por ejemplo, agendamiento de cita).

```json
{
  "event": "call.ended",
  "eventId": "evt-ended-001",
  "call": {
    "callId": "call-joined-test-123",
    "endReason": "hangup",
    "summary": "El cliente Carlos Gomez acordó una reunión/reunion para el lunes a las 10am.",
    "shortSummary": "Cita agendada"
  }
}
```

### C. Prueba de `call.billed` (Facturación de Llamada)
Envía este payload para registrar la duración de facturación del proveedor.

```json
{
  "event": "call.billed",
  "eventId": "evt-billed-001",
  "call": {
    "callId": "call-joined-test-123",
    "billedDuration": "90s",
    "sipDetails": {
      "billedDuration": "90s"
    }
  }
}
```

---

## 8. Limitaciones Conocidas
- **Clasificación por Palabras Clave:** En este sprint inicial, la clasificación de etapa comercial se realiza usando un algoritmo determinista simple de búsqueda de subcadenas/keywords en los textos provistos por Ultravox, lo cual puede carecer de matices en flujos complejos de diálogo.
- **Normalización de Teléfonos Básica:** El helper de normalización limpia caracteres e inserta prefijo colombiano (+57) por defecto si falta, pero no valida la existencia de números válidos de otros países.

---

## 9. Pendientes para Sprint CRM 2
- **Clasificación por LLM:** Integrar clasificación inteligente mediante análisis semántico con IA de los textos de la llamada.
- **Kanban Board UI:** Diseñar y construir la interfaz gráfica del CRM, visualizando el pipeline comercial de ventas.
- **Edición de Leads y Contactos:** Endpoints para crear/actualizar leads manualmente por un agente humano.
- **Asignación de Tareas:** Implementación y UI del módulo de gestión de tareas (`crm_tasks`).
- **Websockets / Notificaciones:** Alertas en tiempo real cuando un lead avanza de etapa o requiere acción inmediata.
