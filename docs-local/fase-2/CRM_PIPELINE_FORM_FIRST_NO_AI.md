# CRM Pipeline Form-First sin IA

## Objetivo

Este cambio endurece el CRM comercial para que el lead nazca desde el formulario o contexto comercial, no desde eventos tardios del webhook. El webhook de Ultravox solo actualiza el mismo lead asociado a la llamada/contexto y evita duplicados.

No se usa IA para crear, clasificar ni extraer datos.

## Pipeline definido

- `new`: Nuevo
- `contacted`: Contactado
- `connected`: Conectado
- `qualified`: Calificado
- `scheduled`: Agendado
- `follow_up`: En seguimiento
- `not_interested`: No interesado
- `won`: Ganado
- `lost`: Perdido

## Significado de cada etapa

- `new`: lead creado desde formulario, carga manual, campana o integracion antes de intentar contacto.
- `contacted`: ya se inicio el intento de llamada, pero aun no hay conversacion efectiva.
- `connected`: la llamada fue contestada y se establecio conexion real.
- `qualified`: el cliente mostro interes comercial, pidio informacion, cotizacion, demo o propuesta.
- `scheduled`: existe evidencia estructurada de evento de calendario creado.
- `follow_up`: queda accion posterior pendiente, llamada no contestada, buzon, fallo, duda o agenda sin evento real.
- `not_interested`: rechazo explicito temprano o solicitud de no continuar.
- `won`: cierre comercial confirmado manualmente.
- `lost`: oportunidad descartada manualmente o por una regla fuerte futura.

## Reglas automaticas

- Formulario/click-to-call crea o reutiliza contacto y crea/reutiliza un lead abierto en `new`.
- `call.started` mueve a `contacted` solo si ya existe lead.
- `call.joined` mueve a `connected`; si no hay lead pero existe contexto suficiente, crea uno asociado a la llamada.
- `call.ended` actualiza `summary` y `short_summary`, detecta booking real y luego clasifica con reglas deterministicas.
- `call.billed` solo registra actividad si ya existe lead.
- `scheduled` solo ocurre con tool de calendario exitosa y evidencia como `event_id`, `calendar_event_id`, `booking_id`, `appointment_id`, `start_time`, `dateTime`, `htmlLink` o `hangoutLink`.
- `not_interested` se puede asignar automaticamente con frases deterministicas de rechazo.

## Reglas manuales

- `won` no lo retorna el clasificador ni la ingesta automatica.
- `lost` no se asigna por una llamada normal ni por rechazo simple; el rechazo temprano queda en `not_interested`.
- La API/UI existente puede mover manualmente a `won`, `lost` o `not_interested`.

## No duplicacion

El resolver busca leads en este orden: `external_call_id`, `created_from_call_id`, `last_call_id`, `form_submission_id`, `context_id`, `phone_normalized`, `email`. Si existe un lead abierto para el contacto/contexto, se reutiliza.

## Tests ejecutados

- `python -m unittest test_crm_pipeline_form_first.py`
- `python -m unittest test_crm_ingestion_hardening.py`
- `python -m unittest test_crm_sprint_1.py`
- `python -m unittest test_crm_sprint_2.py`
- `python -m unittest test_sprint1_auth_context.py`
- `python -m unittest test_sprint3_ultravox_ingestion.py`
- `python -m unittest test_sprint4b_dashboard_api.py`
- `python -m unittest test_sprint7a_onboarding.py`
- `python -m compileall app`

## Limitaciones

- No hay lead scoring con IA.
- No hay clasificacion LLM.
- No hay cierre automatico `won`.
- No hay reglas complejas de perdida por multiples intentos.
- No se implemento drag-and-drop ni cambios mayores de UI.

## Proximos pasos

- Validar manualmente en staging con un formulario real y una llamada Ultravox.
- Confirmar en CRM que el flujo formulario -> started -> joined -> ended -> billed queda en un solo lead.
- Agregar reglas futuras de `lost` solo cuando exista evidencia comercial fuerte.
