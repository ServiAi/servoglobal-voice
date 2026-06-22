# CRM Ingestion Hardening sin IA

## Problema resuelto

La ingesta CRM desde webhooks de Ultravox podia crear contactos/leads comerciales por cada evento de la misma llamada. Tambien podia mover un lead a `scheduled` por texto del resumen, aunque no existiera un evento real de agenda.

## Regla de creacion de lead

- `call.started`: persiste analytics en `calls`/`call_events`, pero CRM no crea `CrmContact`, no crea `CrmLead` y no mueve pipeline.
- `call.joined`: crea o resuelve contacto, crea o resuelve un unico lead por llamada y lo deja en `connected`.
- `call.ended`: actualiza un lead existente. Si no existe lead pero `Call.joined_at` existe, crea lead como fallback conectado. Si no hubo conexion, no crea lead comercial.
- `call.billed`: solo crea actividad de facturacion si ya existe lead asociado a la llamada.

La unicidad se protege por servicio y por indice unico parcial en `crm_leads(tenant_id, created_from_call_id)` cuando `created_from_call_id IS NOT NULL`.

## Regla de contexto

El contexto de formulario se persiste en `crm_call_contexts` antes de iniciar la llamada desde los endpoints backend de voz. El frontend no envia `tenant_id`; el backend usa el tenant bootstrap y agrega un `context_id` interno al `templateContext`.

## Prioridad de extraccion

1. `crm_call_contexts`
2. `payload.call.metadata`
3. `payload.metadata`
4. `payload.meta`
5. `payload.call.initialState`
6. `payload.call.initial_state`
7. `payload.call.initialState.context`
8. `payload.call.requestContext`
9. `payload.call.request_context`
10. `payload.call.requestContext.context`
11. `payload.call.customerPhone`
12. `payload.call.phone`
13. `payload.call.sipDetails.from`

No se extraen datos de contacto desde `summary`.

## Regla de scheduled

`scheduled` solo se asigna si `CrmBookingDetectorService` detecta una tool exitosa con nombre aceptado (`crear_evento`, `create_event`, `create_calendar_event`, `schedule_event`, `book_appointment`) y evidencia estructurada como `event_id`, `calendar_event_id`, `booking_id`, `appointment_id`, `htmlLink`, `hangoutLink`, `start`, `start_time` o `dateTime`.

Si el resumen menciona agenda pero no hay evidencia real, no se mueve a `scheduled`; se establece `next_action = confirm_booking` y la etapa queda en `qualified` o `follow_up` segun reglas deterministicas.

## Eventos Ultravox soportados

- `call.started`
- `call.joined`
- `call.ended`
- `call.billed`

## Consulta para inspeccionar payloads reales

```sql
SELECT
  ce.event_type,
  ce.received_at,
  c.external_call_id,
  ce.payload_json
FROM call_events ce
JOIN calls c ON c.id = ce.call_id
WHERE c.external_provider = 'ultravox'
ORDER BY ce.received_at DESC
LIMIT 20;
```

Revisar si el contexto del formulario aparece en:

- `payload.metadata`
- `payload.meta`
- `payload.call.metadata`
- `payload.call.initialState`
- `payload.call.initial_state`
- `payload.call.requestContext`
- `payload.call.request_context`
- `payload.call.requestContext.context`

## Tests ejecutados

- `python -m unittest test_crm_ingestion_hardening.py`
- `python -m unittest test_crm_sprint_1.py test_crm_sprint_2.py test_sprint3_ultravox_ingestion.py`
- `python -m unittest test_crm_ingestion_hardening.py test_sprint1_auth_context.py test_sprint4b_dashboard_api.py test_sprint7a_onboarding.py`
- `python -m compileall app`

## Limitaciones

- La deteccion de booking es estrictamente estructurada; si el proveedor cambia el shape de tool calls, debe agregarse el nuevo path al detector.
- El fallback por telefono en `crm_call_contexts` solo toma un contexto no ambiguo de los ultimos 30 minutos.

## IA futura

No se implemento IA. A futuro se podria agregar scoring o extraccion desde transcript, pero debe ser un sprint separado y no debe cambiar la regla de `scheduled` sin evidencia real de agenda.
