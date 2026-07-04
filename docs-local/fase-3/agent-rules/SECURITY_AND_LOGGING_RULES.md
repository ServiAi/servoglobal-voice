# Seguridad y logging - Sprint 3

## Prohibido loguear

No loguear:

- Authorization headers.
- Bearer tokens.
- API keys.
- Access tokens.
- Refresh tokens.
- Client secrets.
- `VOICE_TOOL_SHARED_SECRET`.
- Payloads completos de proveedores.
- Telefonos completos.
- Correos completos.
- Nombres completos de clientes.
- Contenido completo de mensajes.
- Attachments.
- Base64.
- HTML completo.

## Permitido loguear

Se permite loguear:

- `tenant_id`
- `lead_id`
- `contact_id`
- `provider`
- `event_type`
- `status_code`
- `status`
- `resource_id`
- Error sanitizado.
- `provider_message_id` o `provider_call_id` si no contiene secreto.

## Secretos

Todo secreto por tenant debe cifrarse con `SecretManagerService`.

Nunca devolver secretos al frontend.

Las respuestas deben usar:

```json
{
  "has_secret": true
}
```

## Frontend tenant

El frontend tenant nunca debe enviar:

```text
tenant_id
```

El backend debe usar:

```python
context.tenant.id
```

## Endpoints internos

Todo endpoint usado por proveedor, agente o sistema interno debe tener proteccion:

* HMAC.
* Shared secret.
* JWT interno.
* Firma del proveedor.

## Webhooks

Todo webhook debe:

* Validar firma o secreto cuando el proveedor lo permita.
* No guardar payload completo.
* Extraer solo metadata segura.
* Registrar eventos en `tenant_integration_events`.
* Registrar activity CRM si aplica.
* Ser idempotente cuando sea posible.

## Validacion obligatoria

Antes de entregar cambios:

```bash
rg "Authorization|Bearer|api_key|access_token|refresh_token|client_secret|VOICE_TOOL_SHARED_SECRET|payload_data|client_phone|client_email|client_name" backend/app backend/test frontend
```

Revisar manualmente los resultados y confirmar que los matches son esperados.
