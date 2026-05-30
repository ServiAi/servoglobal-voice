# Planes y consumo por tenant

## Alcance

Esta fase agrega planes comerciales, consumo de minutos, alertas internas,
bloqueo por limite y comparativa de ahorro dentro del dashboard de metricas.
La landing publica no forma parte de este flujo.

## Planes

| plan_key | Label | Minutos incluidos | Precio ServiGlobal |
| --- | --- | ---: | ---: |
| `web_conversion` | Plan Web Conversion | 2000 | USD 0.16/min |
| `voice_cloud_pbx` | Plan Voice Cloud / PBX | 2000 | USD 0.18/min |
| `enterprise` | Enterprise | configurable, minimo 2000 | configurable entre USD 0.14 y USD 0.15/min |

Decision administrativa: los planes estandar quedan bloqueados sin override
manual para evitar drift de facturacion. Enterprise es el unico plan editable.

## Modelo de datos

La persistencia vive en tablas separadas:

- `tenant_billing_plans`: plan activo del tenant, minutos incluidos, precio,
  estado de consumo, periodo de facturacion y umbrales.
- `tenant_usage_alerts`: alertas visuales persistentes por tenant, periodo y
  tipo de alerta. La unicidad evita duplicados por periodo.
- `external_provider_pricing`: precios de referencia de proveedores externos,
  con fuente, notas y soporte para precio manual o rango.

`calls.billed_minutes` se mantiene como fuente de verdad. El plan guarda estado
y periodo; no duplica minutos usados. Los valores monetarios se calculan en
backend con `Decimal` y columnas `Numeric`.

## Calculo de consumo

Para el periodo activo:

- `minutes_used = sum(calls.billed_minutes)` del tenant.
- `billed_minutes = null` no suma.
- `normalized_status = in_progress` no suma aunque haya datos parciales.
- Si llega billing tardio por webhook, el siguiente recalculo toma el nuevo
  valor desde `calls`.
- `minutes_remaining = included_minutes - minutes_used`.
- `usage_percent = minutes_used / included_minutes * 100`.
- `amount_spent_usd = minutes_used * price_per_minute_usd`.

## Estados y bloqueo

Estados de uso:

- `normal`: consumo menor al 80%.
- `approaching_limit`: consumo desde 80% y menor a 100%.
- `limit_reached`: calculo exacto al llegar a 100%.
- `over_limit`: calculo sobre 100%.
- `suspended_usage_limit`: estado persistido cuando se alcanza o supera el
  limite y el tenant queda bloqueado por consumo.

Cuando el tenant llega al 100%, `tenant.status` pasa a
`suspended_usage_limit`. Los usuarios externos pueden entrar al dashboard para
ver el bloqueo y consumo en modo lectura. Los admins internos conservan acceso
administrativo para revisar, cambiar plan y reactivar. Los endpoints de creacion
de llamadas hacia Ultravox devuelven `402 Payment Required` con
`Tenant minute package exhausted`. Los webhooks tardios de Ultravox no se
bloquean.

## Alertas

Se generan alertas internas persistentes:

- `warning_80`: `usage_percent >= 80`.
- `warning_90`: `usage_percent >= 90`.
- `limit_reached`: `usage_percent >= 100`.

La clave unica `(tenant_id, alert_type, billing_period_start)` evita que cargar
el dashboard cree alertas repetidas.

## Comparativa

La comparativa calcula:

- `estimated_cost_usd = minutes_used * provider_price_per_minute_usd`.
- `serviglobal_cost_usd = minutes_used * tenant_price_per_minute_usd`.
- `estimated_savings_usd = estimated_cost_usd - serviglobal_cost_usd`.
- `estimated_savings_percent = estimated_savings_usd / estimated_cost_usd * 100`.

Si el precio no es comparable o requiere contrato/manual, el precio queda como
`null` y la UI lo muestra como manual.

## Fuentes de precios externos

Consultado el 2026-05-30:

| Proveedor | Precio usado | Fuente | Nota |
| --- | ---: | --- | --- |
| Retell | USD 0.11/min | https://www.retellai.com/pricing | Estimador oficial; rango pay-as-you-go USD 0.07-0.31/min. |
| Vapi | USD 0.05/min | https://vapi.ai/pricing | Hosting cost; excluye STT, LLM y TTS. |
| Dapta | USD 0.33/min | https://dapta.ai/pricing-2/ | Derivado de plan Pro USD 99 / 100k credits y 333 credits por minuto efectivo. |
| OpenAI Realtime | USD 0.096/min estimado | https://platform.openai.com/docs/models/gpt-realtime y https://platform.openai.com/docs/guides/realtime-costs | Supone 1 minuto de audio de usuario y 1 minuto de audio de asistente con gpt-realtime. |
| Gemini Realtime / Google Live API | USD 0.0225/min estimado | https://ai.google.dev/gemini-api/docs/pricing | Supone Gemini 2.5 Flash Native Audio con 1 minuto de entrada y 1 minuto de salida. |
| Otros / Custom | manual | N/A | Requiere configuracion manual por contrato. |

Los precios externos deben revisarse antes de decisiones comerciales finales.
La tabla `external_provider_pricing` permite ajustar valores sin cambiar codigo.

## Endpoints

Tenant dashboard:

- `GET /api/v1/dashboard/usage`
- `GET /api/v1/dashboard/savings-comparison`

Admin:

- `GET /api/v1/admin/tenants`
- `GET /api/v1/admin/tenants/usage-summary`
- `GET /api/v1/admin/usage-alerts`
- `GET /api/v1/admin/tenants/{tenant_id}/usage`
- `PATCH /api/v1/admin/tenants/{tenant_id}/plan`

## Pendientes no incluidos

- Email, Slack u otros canales externos de notificacion.
- Overage facturable posterior al bloqueo.
- Configuracion UI avanzada para proveedores custom.
