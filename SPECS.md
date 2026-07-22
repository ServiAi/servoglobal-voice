# Especificación vigente de ServiGlobal IA

Este documento describe el producto construido en el repositorio. Los documentos de `docs-local/` conservan el detalle histórico de cada sprint.

## 1. Producto

ServiGlobal IA es una plataforma multitenant de captación, atención y seguimiento comercial con agentes de voz y canales integrados. Combina:

- landing pública y demos;
- aplicación privada con Auth0;
- dashboard analítico;
- CRM operativo;
- integraciones de email, formularios, reservas, WhatsApp y voz;
- administración de tenants, planes y consumo.

## 2. Roles y aislamiento

- `platform_admin`: administra tenants, membresías, agentes, planes e integraciones desde rutas internas.
- `tenant_admin` y usuarios tenant: operan únicamente el tenant resuelto por el contexto autenticado.
- Los endpoints tenant no aceptan `tenant_id` del navegador.
- Toda consulta de negocio debe filtrar por tenant.
- Los endpoints internos y webhooks requieren secreto, firma o autenticación según el proveedor.

## 3. Capacidades funcionales

### Identidad y administración

- Login Auth0, resolución de usuario/membresía y onboarding.
- Alta y mantenimiento de tenants, miembros y agentes.
- Planes, límites de minutos, alertas y métricas de uso.

### Voz y analítica

- Llamadas inbound WebRTC y outbound.
- Ingesta de eventos Ultravox, persistencia idempotente y estados normalizados.
- Resumen, duración, costo, agente y contexto comercial.
- Dashboard con filtros temporales y métricas aisladas por tenant.

### CRM

- Pipeline por etapas, listado y detalle de leads.
- Timeline, notas, tareas y transiciones controladas.
- Métricas comerciales, tablero y acciones pendientes.
- Correlación de llamadas, contactos y contexto de formularios.

### Email y formularios

- Configuración Resend cifrada por tenant y prueba de conexión.
- Preview y envío desde lead con trazabilidad e idempotencia.
- Markdown/MDX limitado a componentes seguros; no ejecuta JavaScript arbitrario.
- Adjuntos almacenados localmente o en S3/MinIO privado.
- Formularios públicos mediante token aleatorio; sólo se persiste su hash y expiración.

### Reservas

- Configuración Cal.com por tenant.
- Consulta de slots, creación, cancelación y reprogramación desde CRM o voz.
- Persistencia en CRM, actividades y eventos de integración.
- Webhook Cal.com para reconciliar cambios.
- Google Calendar sólo ofrece foundation OAuth y conexiones; `events.insert` no está habilitado.

### WhatsApp

- Configuración WhatsApp Cloud API cifrada por tenant.
- Plantillas, envío desde lead, historial de mensajes y estados.
- Webhook Meta con verificación y asociación conservadora a contactos/leads existentes.

### Voz CRM

- Configuración de proveedor Ultravox y agentes por tenant.
- Inicio y consulta de llamadas desde un lead.
- Webhook de proveedor y herramientas internas de disponibilidad/reserva protegidas.

## 4. Requisitos no funcionales

- PostgreSQL como base persistente y Alembic como única fuente de migraciones.
- Secretos cifrados con `INTEGRATIONS_ENCRYPTION_KEY` o el mecanismo específico configurado.
- Logs sin tokens, API keys, payloads completos, HTML, adjuntos ni PII sensible.
- Eventos relevantes registrados en timeline CRM y/o `tenant_integration_events`.
- Operaciones externas con errores sanitizados y estados persistidos.
- Frontend bilingüe, accesible y responsive.

## 5. Límites actuales

- Google Calendar directo no crea eventos; Cal.com sigue siendo el motor de booking activo.
- El editor de email es un textarea asistido, no un WYSIWYG completo.
- El builder y la consulta visual avanzada de respuestas de formularios siguen siendo mínimos.
- Automatizaciones masivas, campañas/broadcasts y creación insegura de leads desde inbound WhatsApp no forman parte del alcance actual.

## 6. Criterio de entrega

Una entrega se considera lista cuando pasan tests backend, compilación Python, lint, typecheck, build frontend, validación de una sola head Alembic y `git diff --check`, además de la revisión manual de seguridad indicada en las reglas del sprint.
