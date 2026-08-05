# Estado funcional del proyecto

Actualizado: 2026-08-04. Fuente: código, migraciones y pruebas presentes en `develop` hasta `dbcdc8e`.

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
| Automatizaciones y notificaciones | Operativa en código | Resumen, capacidades, reglas, destinatarios, entregas, planificación, reintentos, recuperación y worker PostgreSQL. El despliegue del proceso worker debe verificarse por entorno. |
| Voz CRM | Operativa | Configuración de proveedor/agentes, llamadas desde leads, webhook y booking tools. |
| Voice Context Experiences | Foundation | Feature flag `voice_experiences` por tenant, límites validados y administración exclusiva de plataforma. No incluye context schemas ni UI. |
| Planes y consumo | Operativa | Límites, alertas, resumen administrativo y comparación de ahorro. |
| Chatwoot | Legado/compatible | Webhook y acciones existentes; conservar compatibilidad al modificar CRM/mensajería. |

## Persistencia

Las migraciones cubren identidad, analítica, riesgo Auth0, planes/uso, CRM base y contexto de llamadas, Resend/email/formularios, Cal.com/Google Calendar, WhatsApp, voz, disponibilidad de integraciones, notificaciones y grants de funcionalidades tenant. La migración más reciente es `202608040001_tenant_feature_grants.py` y la cadena debe conservar una única head.

## Continuidad: automatizaciones y notificaciones

- La página tenant es `frontend/app/[locale]/crm/settings/notifications/page.tsx` y carga resumen, catálogo, capacidades, reglas, destinatarios, entregas y plantillas WhatsApp en paralelo.
- `NotificationsWorkspace` organiza cuatro pestañas: resumen, reglas, destinatarios y entregas. Los roles `platform_admin` y `tenant_admin` pueden escribir; analistas y viewers sólo consultan.
- Las reglas WhatsApp sólo pueden crearse con plantillas activas sincronizadas desde Meta con estado `APPROVED`. Se validan condiciones numéricas y el mapeo de parámetros obligatorios.
- Todos los campos del formulario de reglas tienen ayuda contextual bilingüe. `FieldHelp` abre desde el ícono de ayuda y cierra tanto al pulsarlo nuevamente como al hacer clic fuera.
- Los diálogos largos conservan tres zonas: encabezado, cuerpo desplazable y footer separado; no volver a introducir footers sticky dentro del área desplazable.
- El backend persiste `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events` y `notification_deliveries`. La planificación es idempotente y el worker usa claims con lease, reintentos, recuperación y estados terminales.
- Los commits `caed429` y `dbcdc8e` sólo cambiaron UI, traducciones y pruebas; no modificaron contratos backend, secretos ni resolución de tenant.

## Pendientes explícitos

- Habilitar Google Calendar `events.insert` sólo en un sprint dedicado con callback, scopes y pruebas completas.
- Evolucionar el builder de formularios y la UI de submissions si el producto lo requiere.
- Mantener separados futuros cambios de WhatsApp y voz.
- Implementar context schemas y UI de Voice Context Experiences sólo en incrementos posteriores; este incremento se limita al feature flag.
- Confirmar que cada entorno con automatizaciones tenga un proceso persistente `python -m app.workers.notification_worker` conectado a PostgreSQL.
- Renovar la sesión Playwright con `npm.cmd run qa:auth` antes de la validación visual si la prueba redirige a la pantalla de login.
- Validar en cada entorno credenciales, URLs públicas, webhooks, CORS y almacenamiento; no asumir que los defaults locales representan producción.

## Evidencia de pruebas

El repositorio contiene cobertura backend específica para identidad, analítica, CRM, dashboard, Resend, assets, formularios, Cal.com, Google Calendar foundation, WhatsApp, voz, webhooks, límites de uso y el pipeline de notificaciones. Este último incluye pruebas de modelos, administración, orquestación, condiciones, variables, claims, reintentos, recuperación, reconciliación, worker y ejecutor WhatsApp. El frontend incluye lint, typecheck, build y `frontend/tests/crm-notifications.spec.ts`; la prueba visual requiere una sesión Auth0 válida. Los resultados históricos están en `docs-local/` y deben ejecutarse nuevamente antes de cada entrega.
