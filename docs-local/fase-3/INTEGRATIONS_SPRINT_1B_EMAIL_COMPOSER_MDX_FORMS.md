# Sprint Integraciones 1B Email Composer MDX/Markdown + Adjuntos + Formularios

## Objetivo

Evolucionar el envio transaccional de Resend desde CRM para componer propuestas con Markdown/MDX controlado, adjuntar activos comerciales, insertar links seguros de formularios publicos y registrar eventos en timeline.

## Alcance

- Composer CRM con editor textarea, preview HTML y texto plano.
- Renderer backend seguro para Markdown/MDX controlado.
- Adjuntos por tenant con upload/list/delete y metadata en `tenant_email_assets`.
- Relacion email-adjuntos en `tenant_email_send_assets`.
- Formularios minimos por tenant con tokens opacos hasheados.
- Pagina publica para responder formularios sin login.
- Timeline para `email_preview_generated`, `email_sent`, `email_failed`, `form_link_sent`, `form_opened` y `form_submitted`.

## Decisiones Tecnicas

- No se agrego una dependencia MDX. Se uso Markdown + componentes/shortcodes controlados con standard library para reducir superficie de ataque.
- El editor frontend se mantiene como `textarea`, suficiente para este sprint.
- Los formularios internos usan un formulario base "Diagnostico comercial"; el builder avanzado queda fuera de alcance.
- Los uploads usan `UploadFile` de FastAPI y `python-multipart`, dependencia estandar para multipart.

## Por Que No Forms Embebidos

Los formularios no se incrustan en email porque muchos clientes bloquean HTML interactivo y porque aumenta el riesgo de captura insegura de datos. El correo solo incluye un boton/enlace HTTPS a una pagina publica con token opaco.

## Markdown/MDX Controlado

Componentes permitidos:

- `Button`
- `Callout`
- `Divider`
- `Signature`
- `KeyValueList` reservado

Tambien se soportan shortcodes:

- `{{button:Texto|https://...}}`
- `{{divider}}`
- `{{signature:Nombre}}`

Se rechazan scripts, iframes, forms, inputs, selects, textareas, style tags, handlers `on*`, imports, exports, `javascript:` y componentes no autorizados.

## Flujo De Adjuntos

1. El usuario carga un archivo permitido.
2. Backend valida extension, MIME y tamano.
3. `StorageService` guarda binario fuera de DB.
4. `tenant_email_assets` guarda metadata.
5. El composer selecciona asset IDs.
6. `EmailSendService` valida tenant, arma adjuntos para Resend y guarda `tenant_email_send_assets`.

## Flujo De Formularios Publicos

1. Tenant/admin crea o usa el formulario por defecto.
2. Composer genera token por lead.
3. Backend guarda solo `sha256(token)`.
4. Email inserta boton con `/forms/public/{token}`.
5. Public page carga formulario sin login.
6. Submit valida token, expiracion y campos requeridos.
7. Respuesta se guarda asociada a lead/contact y se crea actividad CRM.

## Seguridad De Tokens

- Token aleatorio con `secrets.token_urlsafe`.
- Solo hash en DB.
- Expiracion obligatoria.
- URL sin tenant, lead, email ni telefono.
- Token usado queda en estado `used`.

## Endpoints Creados

- `POST /api/v1/integrations/resend/assets`
- `GET /api/v1/integrations/resend/assets`
- `DELETE /api/v1/integrations/resend/assets/{asset_id}`
- `POST /api/v1/admin/tenants/{tenant_id}/integrations/resend/assets`
- `GET /api/v1/admin/tenants/{tenant_id}/integrations/resend/assets`
- `DELETE /api/v1/admin/tenants/{tenant_id}/integrations/resend/assets/{asset_id}`
- `GET /api/v1/forms`
- `POST /api/v1/forms`
- `GET /api/v1/forms/{form_id}`
- `POST /api/v1/forms/{form_id}/tokens`
- `GET /api/v1/admin/tenants/{tenant_id}/forms`
- `POST /api/v1/admin/tenants/{tenant_id}/forms`
- `GET /api/v1/admin/tenants/{tenant_id}/forms/{form_id}`
- `POST /api/v1/admin/tenants/{tenant_id}/forms/{form_id}/tokens`
- `GET /api/v1/public/forms/{token}`
- `POST /api/v1/public/forms/{token}/submit`

## Rutas Frontend

- `/[locale]/crm/settings/forms`
- `/[locale]/admin/tenants/[tenantId]/forms`
- `/[locale]/forms/public/[token]`

## Tests Ejecutados

- `python -m unittest test_email_composer_mdx.py`
- `python -m unittest test_email_assets.py`
- `python -m unittest test_forms_public_links.py`
- `python -m unittest test_crm_email_composer_action.py`
- `python -m unittest test_admin_tenant_integrations.py`
- `python -m unittest test_resend_integration.py`
- `python -m unittest test_crm_email_action.py`
- `python -m unittest test_integrations_base.py`
- `python -m compileall app`
- `npm.cmd run lint`
- `npx.cmd tsc --noEmit --incremental false`
- `npm.cmd run build`

## Riesgos Pendientes

- El builder visual de formularios es intencionalmente minimo.
- `KeyValueList` esta reservado como componente permitido, pero no tiene render especializado aun.
- La lista de submissions queda para una iteracion de UI posterior.
- El build muestra warnings existentes de Next/Node sobre `tailwind.config.ts` y edge runtime.

## Mejoras Futuras

- Builder de formularios completo.
- Biblioteca de snippets controlados para propuestas.
- Historial visual de submissions por lead.
- UI de administracion avanzada de assets.
