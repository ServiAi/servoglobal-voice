# Estado funcional del proyecto

Actualizado: 2026-08-21. Fuente: código, migraciones y pruebas del repositorio.

| Área | Estado | Implementación actual |
| --- | --- | --- |
| Landing e i18n | Operativa | Landing bilingüe, pricing, demos, formularios y contenido SEO. |
| Auth0 y tenants | Operativa | Login, contexto privado, onboarding, administración, membresías y agentes. |
| Dashboard | Operativa | KPIs, tendencias, distribuciones, heatmap, llamadas recientes, uso y ahorro. |
| CRM | Operativa | Pipeline, leads, detalle, timeline, notas, tareas y dashboard comercial con paneles separados de rendimiento Ultravox y capacidad SIP por tenant. |
| Ingesta Ultravox | Operativa | Eventos, llamadas, estados, resumen, costos y correlación CRM. |
| Resend | Operativa | Configuración tenant, prueba, templates, preview, envío y trazabilidad. |
| Composer y assets | Operativa | Markdown/MDX seguro, resumen de llamada, adjuntos local/S3 y formularios públicos. |
| Cal.com | Operativa | Slots, booking, cancelación, reprogramación y webhook. |
| Google Calendar | Parcial | OAuth foundation, listado y desconexión; creación directa de eventos deshabilitada. |
| WhatsApp Cloud | Operativa | Configuración, plantillas, envío CRM, mensajes, estados y webhook. |
| Automatizaciones y notificaciones | Operativa en código | Contratos versionados de eventos, builder dinámico, dry-run sin envío, reglas, destinatarios, entregas, planificación, reintentos, recuperación y worker PostgreSQL. El despliegue del proceso worker debe verificarse por entorno. |
| Voz CRM | Operativa en código | Configuración de proveedor/agentes, rutas SIP cifradas por tenant, aprovisionamiento automático y versionado de endpoints PJSIP, llamadas WebRTC y callbacks salientes mediante IDT, webhook y booking tools. El agente local del PBX debe instalarse por entorno. |
| Voice Context Experiences | Runtime público WebRTC implementado en código | Feature flag, snapshots, submissions y context session one-shot; launch Ultravox tenant-scoped con recovery-first, leases, recovery por `joined`/`ended`, webhook firmado/deduplicado, billing real por `billedDuration`, CRM monotónico, concurrencia PostgreSQL y preflight de micrófono. `submissions=true`; `calls=true`. Ver `docs-local/fase-4/VOICE_EXPERIENCE_WEBRTC_RUNTIME.md`. |
| Planes y consumo | Operativa | Límites, alertas, resumen administrativo y comparación de ahorro. |
| Chatwoot | Legado/compatible | Webhook y acciones existentes; conservar compatibilidad al modificar CRM/mensajería. |

## Persistencia

Las migraciones cubren identidad, analítica, riesgo Auth0, planes/uso, CRM base y contexto de llamadas, Resend/email/formularios, Cal.com/Google Calendar, WhatsApp, voz, disponibilidad de integraciones, notificaciones, grants tenant, context submissions, runtime WebRTC y rutas SIP/callbacks salientes. La migración más reciente es `202608210001_asterisk_route_provisioning.py` y la cadena debe conservar una única head.

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
- Verificar por entorno los prerequisitos Ultravox tenant (API key, webhook secret, agente compatible con `user_context` y eventos webhook) antes de habilitar el runtime público.
- Etapa 0 (`fix/voice-experience-functional-alignment`): `get_current_published_version()` es fail-closed por `published_version_id`; `PUT` bloquea cambio de agente con historial; `DELETE` elimina definitivamente experiencias archivadas junto con versiones, submissions, valores, sesiones y runtime asociados; `/api/v1/calls` quedó tipado y sanitizado. Pendiente: endurecer `/api/v1/call-outbound` con el mismo criterio.
- Callback saliente multitenant: cada tenant configura una ruta SIP cifrada y Caller ID autorizado; el backend genera el usuario SIP estable `route-<uuid>` para que coincida con el endpoint PJSIP y la interfaz lo mantiene en solo lectura. Las experiencias publicadas pueden solicitar una llamada idempotente usando sólo el token de contexto. El backend normaliza E.164 para CO, MX, AR, PA, CL, EC, PE y US, y el worker inicia Ultravox con la credencial SIP del tenant. `call.ended` libera inmediatamente la capacidad y el worker reconcilia con Ultravox los estados activos cuando falta el webhook, con cierre máximo de seguridad configurable. El dashboard muestra ocupación, cupos, saturaciones y liberaciones con eventos sanitizados por tenant; sólo administradores enlazan a la configuración, mientras analyst/viewer permanecen en lectura. El agente local de Asterisk reconcilia un include PJSIP administrado y reporta cada revisión; una ruta pendiente o fallida no puede originar llamadas. WebRTC permanece independiente.
- El aviso de cambios sin guardar cubre recarga/cierre y navegación mediante enlaces; el historial nativo atrás/adelante sigue como limitación conocida de App Router hasta disponer de un hook estable.
- El listado consulta el historial por experiencia para mostrar su conteo. Si `max_experiences` crece y esto se vuelve un cuello de botella, el backend deberá incluir el conteo en la respuesta del listado.
- El inventario de Voice Experiences muestra las experiencias publicadas como listas para compartir y ofrece abrir o copiar su enlace público desde cada tarjeta; el enlace usa siempre `experience.default_locale`, no el idioma que esté navegando el administrador.
- El tema de una experiencia admite `background_color` y `color_scheme` (`light`/`dark`, `light` por defecto) además de `logo_url`, `primary_color` y `layout`; se versiona con la publicación y se renderiza igual en la vista previa del editor y en el formulario público mediante `resolveVoiceTheme`.
- Cada experiencia publicada expone `/{locale}/voice/{slug}/embed`, la misma página pública sin cabecera de sitio ni márgenes de página completa, pensada para `<iframe>`; comunica su altura al padre vía `postMessage` (`ResizeObserver`) y sólo esa ruta declara `Content-Security-Policy: frame-ancestors *`. El panel "Compartir / Incrustar" del listado genera enlace, y fragmentos de código (HTML/React/iframe) para incrustación inline, botón flotante o modal, usando el SDK vanilla `frontend/public/voice-embed.v1.js` (`window.VoiceEmbed`). La configuración de texto/posición del botón flotante y el selector del disparador del modal son sólo del fragmento generado; no se persisten en backend.
- El editor permite seleccionar snapshots históricos para previsualizarlos, restaurarlos como borrador y eliminar únicamente versiones antiguas sin referencias; las versiones actual, más reciente, referenciadas o archivadas permanecen protegidas.
- En Agente y contexto, las versiones de esquema se pueden abrir desde el historial; las versiones activas o archivadas se editan mediante un borrador nuevo o existente. Abrir/crear el borrador es idempotente, lo selecciona automáticamente y evita conflictos cuando ya existe otra versión draft.
- Confirmar que cada entorno con automatizaciones tenga un proceso persistente `python -m app.workers.notification_worker` conectado a PostgreSQL.
- Renovar la sesión Playwright con `npm.cmd run qa:auth` antes de la validación visual si la prueba redirige a la pantalla de login.
- Validar en cada entorno credenciales, URLs públicas, webhooks, CORS y almacenamiento; no asumir que los defaults locales representan producción.

## Evidencia de pruebas

El repositorio contiene cobertura backend específica para identidad, analítica, CRM, dashboard, Resend, assets, formularios, Cal.com, Google Calendar foundation, WhatsApp, voz, context schemas, Voice Experiences, resolución pública y snapshots publicados, webhooks, límites de uso y el pipeline de notificaciones; incluye la compatibilidad del tema con snapshots anteriores a `background_color`/`color_scheme`. El frontend incluye lint, typecheck, build, pruebas privadas y `frontend/tests/public-voice-experiences.spec.ts` y `frontend/tests/public-voice-embed.spec.ts` (tema claro/oscuro/fondo personalizado, chrome de la ruta `/embed`, resize por `postMessage` contra un host HTTP real y los tres modos del SDK); la ruta pública no requiere sesión Auth0. Los resultados históricos están en `docs-local/` y deben ejecutarse nuevamente antes de cada entrega.
