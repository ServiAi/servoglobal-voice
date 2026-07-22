# Estado funcional del proyecto

Actualizado: 2026-07-22. Fuente: código y migraciones presentes en la rama base `develop` al iniciar esta actualización.

| Área | Estado | Implementación actual |
| --- | --- | --- |
| Landing e i18n | Operativa | Landing bilingüe, pricing, demos, formularios y contenido SEO. |
| Auth0 y tenants | Operativa | Login, contexto privado, onboarding, administración, membresías y agentes. |
| Dashboard | Operativa | KPIs, tendencias, distribuciones, heatmap, llamadas recientes, uso y ahorro. |
| CRM | Operativa | Pipeline, leads, detalle, timeline, notas, tareas, métricas y dashboard comercial. |
| Ingesta Ultravox | Operativa | Eventos, llamadas, estados, resumen, costos y correlación CRM. |
| Resend | Operativa | Configuración tenant, prueba, templates, preview, envío y trazabilidad. |
| Composer y assets | Operativa | Markdown/MDX seguro, resumen de llamada, adjuntos local/S3 y formularios públicos. |
| Cal.com | Operativa | Slots, booking, cancelación, reprogramación y webhook. |
| Google Calendar | Parcial | OAuth foundation, listado y desconexión; creación directa de eventos deshabilitada. |
| WhatsApp Cloud | Operativa | Configuración, plantillas, envío CRM, mensajes, estados y webhook. |
| Voz CRM | Operativa | Configuración de proveedor/agentes, llamadas desde leads, webhook y booking tools. |
| Planes y consumo | Operativa | Límites, alertas, resumen administrativo y comparación de ahorro. |
| Chatwoot | Legado/compatible | Webhook y acciones existentes; conservar compatibilidad al modificar CRM/mensajería. |

## Persistencia

Las migraciones cubren identidad, analítica, riesgo Auth0, planes/uso, CRM base y contexto de llamadas, Resend/email/formularios, Cal.com/Google Calendar, WhatsApp y voz. La migración más reciente es `202607030002_integrations_3b_voice_crm_actions.py` y la cadena debe conservar una única head.

## Pendientes explícitos

- Habilitar Google Calendar `events.insert` sólo en un sprint dedicado con callback, scopes y pruebas completas.
- Evolucionar el builder de formularios y la UI de submissions si el producto lo requiere.
- Mantener separados futuros cambios de WhatsApp y voz.
- Validar en cada entorno credenciales, URLs públicas, webhooks, CORS y almacenamiento; no asumir que los defaults locales representan producción.

## Evidencia de pruebas

El repositorio contiene cobertura backend específica para identidad, analítica, CRM, dashboard, Resend, assets, formularios, Cal.com, Google Calendar foundation, WhatsApp, voz, webhooks y límites de uso. El frontend incluye lint, typecheck, build y Playwright visual. Los resultados históricos están en `docs-local/`; deben ejecutarse nuevamente antes de cada entrega.
