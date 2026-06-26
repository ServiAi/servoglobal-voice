# CRM operativo - checklist de cierre

## tenant_viewer

- Puede abrir el detalle del lead.
- Puede ver datos del contacto, calificacion comercial, timeline y tareas.
- No ve el boton Editar Lead.
- No ve quick actions.
- No ve formularios para crear nota o tarea.
- No puede completar ni eliminar tareas.

## tenant_analyst

- Puede abrir el detalle del lead.
- Puede crear nota.
- Puede crear tarea.
- Puede completar tareas.
- Ve quick actions operativas permitidas.
- No ve Editar Lead.
- No ve acciones terminales para marcar ganado, perdido o no interesado.
- No puede eliminar tareas.

## tenant_admin

- Puede editar lead.
- Puede cerrar lead con motivo.
- Puede borrar lead individual.
- No puede ejecutar borrado masivo.

## platform_admin

- Puede editar lead.
- Puede cerrar lead con motivo.
- Puede ejecutar borrado masivo.
- Ve todas las acciones permitidas del CRM.

## Fechas

- Los inputs siguen mostrando fechas en formato `YYYY-MM-DD`.
- Al filtrar desde `2026-06-01`, la URL envia `date_from=2026-06-01T00:00:00Z`.
- Al filtrar hasta `2026-06-30`, la URL envia `date_to=2026-06-30T23:59:59Z`.
- La lista conserva la URL filtrada al recargar.
- El backend limita resultados al rango completo del dia.

## Voicemail

- Una llamada con `normalized_status=voicemail` queda en etapa Buzon de voz.
- La metrica `voicemail_leads` aumenta.
- La metrica `follow_up_leads` no aumenta por llamadas voicemail.
- El pipeline muestra el lead en Buzon de voz.
