# Sprint Integraciones 1B.1 Email Composer Pro + Resumen de llamada

## Objetivo

Extender el Email Composer transaccional del CRM con un editor Markdown/MDX controlado mas completo y soporte para traer el resumen de llamada del lead, insertarlo en el cuerpo o adjuntarlo como archivo `.md` / `.txt`.

## Alcance

- Composer CRM con toolbar, panel de variables, snippets, preview HTML y texto plano.
- Insercion de resumen completo o version corta mediante variables controladas.
- Generacion de adjunto de resumen de llamada usando `StorageService`.
- Uso preservado de adjuntos locales o MinIO/S3 segun `EMAIL_ASSETS_STORAGE_DRIVER`.
- Timeline CRM con metadata segura para resumen insertado y resumen adjuntado.

## Herramientas Del Editor

La toolbar inserta sintaxis segura para:

- H1 / H2.
- Negrita e italica.
- Lista con vinetas y lista numerada.
- Cita.
- Link HTTP(S).
- `Button`.
- `Callout`.
- `Divider`.
- `Signature`.
- Bloque de resumen de llamada.

## Componentes MDX Soportados

Se mantiene el renderer controlado existente. Componentes permitidos:

- `Button`
- `Callout`
- `Divider`
- `Signature`
- `KeyValueList` reservado

No se permite JavaScript, imports/exports, `script`, `iframe`, `form`, inputs, handlers `on*`, `javascript:` ni componentes arbitrarios.

## Variables Disponibles

- `{{contact_name}}`
- `{{contact_email}}`
- `{{company}}`
- `{{interest}}`
- `{{industry}}`
- `{{use_case}}`
- `{{volume}}`
- `{{pain_point}}`
- `{{source}}`
- `{{campaign}}`
- `{{lead_id}}`
- `{{call_summary}}`
- `{{call_summary_short}}`
- `{{last_call_date}}`
- `{{call_duration_seconds}}`
- `{{form_link}}`

## Como Se Obtiene El Resumen

`CallSummaryService` busca en este orden:

1. Ultima actividad CRM del lead con `summary` o `shortSummary` en `payload_json`.
2. Ultima llamada asociada al lead (`last_call_id` / `created_from_call_id`).
3. `CrmCallContext.raw_context_json` asociado por `context_id`.
4. `CrmLead.summary` / `CrmLead.short_summary`.

Si no encuentra resumen responde `status=not_found`.

## Insercion En El Cuerpo

El frontend llama:

```http
GET /api/v1/crm/leads/{lead_id}/call-summary
```

Si hay resumen, el composer inserta:

```md
## Resumen de la llamada

{{call_summary}}
```

Tambien puede insertar `{{call_summary_short}}`. El renderer resuelve esas variables al hacer preview o enviar.

## Generacion Como Adjunto

El frontend llama:

```http
POST /api/v1/crm/leads/{lead_id}/call-summary/asset
```

Payload:

```json
{ "format": "md" }
```

Formatos soportados: `md`, `txt`.

El asset se guarda en `tenant_email_assets` y el binario se guarda con:

```text
tenants/{tenant_id}/email-assets/{asset_id}/resumen-llamada-{lead_id}.{format}
```

El asset queda seleccionado automaticamente como adjunto del email.

## Seguridad

- No se loguea el resumen completo.
- No se loguean adjuntos ni base64.
- No se exponen credenciales ni tokens sensibles al frontend.
- No hay URLs publicas para assets.
- No se permite cross-tenant: todas las consultas filtran por `tenant_id`.
- No se genera archivo si no hay resumen.
- El timeline solo guarda metadata segura: `email_asset_id`, `format` o `variant`.

## Endpoints

- `GET /api/v1/crm/leads/{lead_id}/call-summary`
- `POST /api/v1/crm/leads/{lead_id}/call-summary/inserted`
- `POST /api/v1/crm/leads/{lead_id}/call-summary/asset`
- Se preserva `POST /api/v1/crm/leads/{lead_id}/actions/email`.

## Tests Ejecutados

Pendiente de cierre final en validacion del sprint.

## Riesgos Pendientes

- `form_link` se mantiene como variable disponible para snippets, pero el flujo seguro recomendado sigue siendo generar el token y pegar el link real desde el boton de formulario.
- El editor sigue siendo textarea controlado con toolbar, no un editor visual WYSIWYG.

