# Voice Context Experiences - feature grants

## Alcance

Este primer incremento agrega exclusivamente el feature flag `voice_experiences` por tenant. No incluye schemas de contexto, UI, formularios, WebRTC, WhatsApp, despliegue, dominios ni analitica.

## Modelo

`tenant_feature_grants` guarda un registro por `tenant_id` y `feature_key`, con estado habilitado, limites JSON, usuario de plataforma que realizo el ultimo cambio y timestamps. La restriccion unica evita duplicados y los indices permiten buscar por tenant o funcionalidad.

La unica funcionalidad admitida actualmente es `voice_experiences`. Sus limites obligatorios son enteros positivos:

- `max_experiences`
- `max_context_fields`

## Endpoints

- `GET /api/v1/admin/tenants/{tenant_id}/features`: lista grants persistidos del tenant.
- `PUT /api/v1/admin/tenants/{tenant_id}/features/voice-experiences`: crea o actualiza el grant sin duplicarlo.

Payload del `PUT`:

```json
{
  "enabled": true,
  "limits": {
    "max_experiences": 5,
    "max_context_fields": 20
  }
}
```

## Seguridad

Los endpoints exigen `context.user.is_internal == true`. Ningún rol de membresía tenant, incluido `platform_admin`, concede acceso por sí solo. El tenant objetivo proviene del path administrativo y se valida contra la base de datos. No existe endpoint tenant ni se exponen `tenant_id`, `enabled_by_user_id`, credenciales o datos personales en la respuesta.

## Tests

`backend/test_tenant_features.py` cubre alta, actualizacion idempotente, deshabilitacion, rechazo de keys desconocidas, tenant inexistente, aislamiento multitenant, autorizacion administrativa, validacion/persistencia de limites y respuesta segura.

## Pendientes

- Definir e implementar context schemas en un incremento posterior.
- Consumir `require_enabled` desde futuras operaciones de Voice Context Experiences.
- Crear UI administrativa solo cuando se autorice su incremento.
