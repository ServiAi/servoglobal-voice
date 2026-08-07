# Estado funcional del proyecto

Actualizado: 2026-08-06. Fuente: código, migraciones y pruebas del repositorio.

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
| Automatizaciones y notificaciones | Operativa en código | Contratos versionados de eventos, builder dinámico, dry-run sin envío, reglas, destinatarios, entregas, planificación, reintentos, recuperación y worker PostgreSQL. El despliegue del proceso worker debe verificarse por entorno. |
| Voz CRM | Operativa | Configuración de proveedor/agentes, llamadas desde leads, webhook y booking tools. |
| Voice Context Experiences | Builder privado y lectura pública implementados en código | Feature flag, schemas versionados, administración tenant y UI bilingüe privada. Una versión publicada puede consultarse sin Auth0 en `/{locale}/voice/{slug}` mediante un DTO sanitizado, histórico y fail-closed. La página pública es responsive, no indexable y estrictamente de solo lectura: no captura datos ni inicia llamadas/WebRTC. Ver `docs-local/fase-4/VOICE_EXPERIENCE_PUBLIC_RUNTIME.md`. |
| Planes y consumo | Operativa | Límites, alertas, resumen administrativo y comparación de ahorro. |
| Chatwoot | Legado/compatible | Webhook y acciones existentes; conservar compatibilidad al modificar CRM/mensajería. |

## Persistencia

Las migraciones cubren identidad, analítica, riesgo Auth0, planes/uso, CRM base y contexto de llamadas, Resend/email/formularios, Cal.com/Google Calendar, WhatsApp, voz, disponibilidad de integraciones, notificaciones y grants de funcionalidades tenant. La migración más reciente es `202608050003_notification_rule_event_schemas.py` y la cadena debe conservar una única head.

## Continuidad: automatizaciones y notificaciones

- La página tenant es `frontend/app/[locale]/crm/settings/notifications/page.tsx` y carga resumen, catálogo, capacidades, reglas, destinatarios, entregas y plantillas WhatsApp en paralelo.
- `NotificationsWorkspace` organiza cuatro pestañas: resumen, reglas, destinatarios y entregas. Los roles `platform_admin` y `tenant_admin` pueden escribir; analistas y viewers sólo consultan.
- Las reglas WhatsApp sólo pueden crearse con plantillas activas sincronizadas desde Meta con estado `APPROVED`. El registro central relaciona capacidad/evento con campos tipados, operadores, formatos, rutas de destinatario, ejemplo seguro y versión.
- El modal carga eventos según capacidad, genera condiciones y variables desde el contrato, conserva `all`/`any`, detecta rutas obsoletas y ofrece un dry-run que no crea entregas ni envía WhatsApp.
- Todos los campos del formulario de reglas tienen ayuda contextual bilingüe. `FieldHelp` abre desde el ícono de ayuda y cierra tanto al pulsarlo nuevamente como al hacer clic fuera.
- Los diálogos largos conservan tres zonas: encabezado, cuerpo desplazable y footer separado; no volver a introducir footers sticky dentro del área desplazable.
- El backend persiste `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events` y `notification_deliveries`. La planificación es idempotente y el worker usa claims con lease, reintentos, recuperación y estados terminales.
- Los commits `caed429` y `dbcdc8e` sólo cambiaron UI, traducciones y pruebas; no modificaron contratos backend, secretos ni resolución de tenant.

## Pendientes explícitos

- Habilitar Google Calendar `events.insert` sólo en un sprint dedicado con callback, scopes y pruebas completas.
- Evolucionar el builder de formularios y la UI de submissions si el producto lo requiere.
- Mantener separados futuros cambios de WhatsApp y voz.
- Completar en incrementos posteriores la captura pública, consentimiento persistido y runtime de llamada de Voice Experiences; la superficie pública actual sólo representa el snapshot publicado y mantiene ambas capacidades deshabilitadas.
- Etapa 0 (`fix/voice-experience-functional-alignment`): `get_current_published_version()` es fail-closed por `published_version_id`; `PUT` bloquea cambio de agente con historial; `DELETE` sólo elimina archivadas sin historial; `/api/v1/calls` quedó tipado y sanitizado. Pendiente: endurecer `/api/v1/call-outbound` con el mismo criterio.
- El aviso de cambios sin guardar cubre recarga/cierre y navegación mediante enlaces; el historial nativo atrás/adelante sigue como limitación conocida de App Router hasta disponer de un hook estable.
- El listado consulta el historial por experiencia para mostrar su conteo. Si `max_experiences` crece y esto se vuelve un cuello de botella, el backend deberá incluir el conteo en la respuesta del listado.
- Confirmar que cada entorno con automatizaciones tenga un proceso persistente `python -m app.workers.notification_worker` conectado a PostgreSQL.
- Renovar la sesión Playwright con `npm.cmd run qa:auth` antes de la validación visual si la prueba redirige a la pantalla de login.
- Validar en cada entorno credenciales, URLs públicas, webhooks, CORS y almacenamiento; no asumir que los defaults locales representan producción.

## Evidencia de pruebas

El repositorio contiene cobertura backend específica para identidad, analítica, CRM, dashboard, Resend, assets, formularios, Cal.com, Google Calendar foundation, WhatsApp, voz, context schemas, Voice Experiences, resolución pública y snapshots publicados, webhooks, límites de uso y el pipeline de notificaciones. El frontend incluye lint, typecheck, build, pruebas privadas y `frontend/tests/public-voice-experiences.spec.ts`; la ruta pública no requiere sesión Auth0. Los resultados históricos están en `docs-local/` y deben ejecutarse nuevamente antes de cada entrega.
