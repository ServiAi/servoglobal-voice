# Configuración y operación

## Entorno local

1. Levante PostgreSQL con `docker compose up -d postgres`.
2. Cree `backend/.env` y `frontend/.env.local` desde los ejemplos, sin versionarlos.
3. Instale dependencias, ejecute `alembic upgrade head` y arranque FastAPI.
4. Instale dependencias frontend y arranque Next.js.

Variables base:

- Backend: `DATABASE_URL`, `PORT`, Auth0, Ultravox y `INTEGRATIONS_ENCRYPTION_KEY`.
- Frontend: `NEXT_PUBLIC_API_URL`, Auth0 y Turnstile cuando se use la demo pública.
- Integraciones opcionales: Cal.com, Google Calendar, Resend/storage, WhatsApp y secretos de webhooks/herramientas internas. Chatwoot ya no usa variables de entorno globales para credenciales por tenant (`CHATWOOT_API_TOKEN`/`CHATWOOT_ACCOUNT_ID`/`CHATWOOT_INBOX_ID` fueron retiradas); se configura por tenant en `Settings → Integrations → Chatwoot`. La excepción es el modo "managed": `CHATWOOT_PLATFORM_API_TOKEN` (token de Super Admin/Platform App de la instancia compartida) y `BACKEND_PUBLIC_BASE_URL` (URL pública de este backend, usada para registrar el `outgoing_url` del Agent Bot) son globales y necesarios sólo para `POST /api/v1/integrations/chatwoot/provision`; sin ellos, el modo "external" (formulario manual) sigue funcionando igual.
- Worker de notificaciones: `NOTIFICATION_WORKER_BATCH_SIZE`, `NOTIFICATION_WORKER_POLL_SECONDS`, `NOTIFICATION_WORKER_LEASE_SECONDS`, `NOTIFICATION_WORKER_MAX_ATTEMPTS`, tiempos de retry/jitter y parámetros de recuperación. Los defaults y rangos válidos están en `backend/app/core/config.py`.

Los nombres vigentes y placeholders están en los archivos `.env.example`. Nunca copie valores reales a documentación, logs o commits.

## Base de datos

```powershell
cd backend
alembic heads
alembic upgrade head
alembic current
```

Debe existir una sola head. No ejecute migraciones contra producción desde una sesión local sin autorización explícita y respaldo operativo.

Las migraciones de notificaciones son:

- `202607240001_add_tenant_notification_foundation.py`.
- `202607270001_add_notification_worker_state.py`.
- `202608050003_notification_rule_event_schemas.py` (modo de condiciones y versión del contrato en reglas).

Flow Studio V1 añade `202608310002_whatsapp_flow_studio_v1.py`. No agrega variables ni secretos: usa `WHATSAPP_GRAPH_VERSION`, el token cifrado y el WABA ID ya configurados por tenant. Después de aplicar la migración, valide con un tenant de pruebas: crear borrador, compilar, validar en Meta, publicar, sincronizar estado y clonar a v2. No use credenciales ni WABA de producción desde pruebas locales.

## Worker de notificaciones

El worker requiere PostgreSQL y debe ejecutarse como un proceso separado del servidor FastAPI:

```powershell
cd backend

# Procesar todos los lotes actualmente vencidos y salir
python -m app.workers.notification_worker --once

# Operación persistente
python -m app.workers.notification_worker
```

Antes de habilitarlo en un entorno:

1. Ejecute `alembic upgrade head` y confirme una sola head.
2. Verifique que la configuración WhatsApp del tenant esté activa y que existan plantillas Meta aprobadas.
3. Confirme capacidades y reglas desde `/crm/settings/notifications`.
4. Arranque al menos un worker persistente y compruebe que reclama entregas vencidas.
5. Revise sólo metadata y códigos sanitizados; no registre teléfonos, mensajes, tokens, payloads o claim tokens.

El worker procesa cada lote reclamado hasta terminar y sólo atiende la señal de apagado antes de reclamar el siguiente. Los claims vencidos se recuperan según el lease y la política de recuperación configurada.

## Pruebas y calidad

```powershell
cd backend
python -m unittest discover -p "test_*.py"
python -m compileall app

cd ..\frontend
npm.cmd run lint
npx.cmd tsc --noEmit --incremental false
npm.cmd run build
npm.cmd run qa:visual

cd ..
git diff --check
```

Para validar únicamente automatizaciones y notificaciones:

```powershell
cd backend
python -m unittest test_notification_event_schemas test_notification_admin test_notification_models test_notification_orchestrator test_notification_event_pipeline test_notification_delivery_claim_service test_notification_delivery_recovery test_notification_retry_policy test_notification_schedule_reconciliation test_notification_worker test_whatsapp_notification_executor

cd ..\frontend
npx.cmd playwright test tests/crm-notifications.spec.ts --project=crm-visual
```

Playwright usa `frontend/playwright/.auth/user.json`. Si la prueba abre "Te damos la bienvenida" o espera indefinidamente la pestaña Reglas, renueve la sesión con `npm.cmd run qa:auth` y vuelva a ejecutar el proyecto `crm-visual`.

`test_notification_worker_postgres` valida claims concurrentes contra una base real. Ejecútela por separado y sólo con `DATABASE_URL` configurada hacia PostgreSQL de pruebas; no use una base compartida ni de producción.

Ejecute pruebas focalizadas durante el desarrollo y la suite completa antes de merge. Playwright requiere el entorno definido en su configuración y, según el proyecto, sesión Auth0 preparada.

## Despliegue

### Callback de voz saliente mediante IDT Express

1. Aplique `202608210001_asterisk_route_provisioning.py` y confirme una sola head de Alembic.
2. Instale `phonenumbers` desde `backend/requirements.txt`.
3. Configure en Integraciones la ruta SIP del tenant: host/puerto PBX, contraseña SIP, Caller ID autorizado, país predeterminado, países habilitados y concurrencia. El backend genera un usuario inmutable `route-<uuid>` que coincide con el endpoint PJSIP; la interfaz lo muestra en solo lectura. La contraseña queda cifrada y no vuelve a mostrarse.
4. Configure `ASTERISK_PROVISIONER_SHARED_SECRET` en el backend con un secreto aleatorio dedicado. Instale en el PBX el agente `python -m app.workers.asterisk_provisioner` usando las plantillas de `ops/asterisk/`. El agente consulta el estado deseado, genera atómicamente `/etc/asterisk/pjsip.d/serviglobal-tenants.conf`, recarga PJSIP, verifica cada endpoint y reporta la revisión. En caso de error restaura el include anterior.

5. La plantilla base `ultravox-tenant` permanece definida manualmente una sola vez en `pjsip.conf`. Añada después de ella este include:

```ini
#include pjsip.d/serviglobal-tenants.conf
```

No edite `serviglobal-tenants.conf`: se sobrescribe en cada reconciliación. La credencial generada coincide con la integración y usa un identificador de ruta opaco. No acepte Caller ID, ruta o tenant desde el formulario. `from-ultravox-tenant` sólo acepta E.164 para CO, MX, AR, PA, CL, EC, PE y US, retira `+`, antepone `IDT_DIVISION` y marca exclusivamente por `idt-out`. Los rechazos no contactan al carrier y los logs no contienen el destino completo.

6. Ejecute también el worker de callbacks como servicio independiente:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.workers.voice_callback_worker
```

El callback usa una cola persistente en PostgreSQL; no requiere Redis, RabbitMQ
ni Celery. `crm_voice_calls` es la fuente de verdad: el endpoint público valida
la solicitud, crea la llamada con estado `requested` y responde `202`. El worker
toma primero las solicitudes más antiguas mediante `SELECT ... FOR UPDATE SKIP
LOCKED`, respeta la concurrencia de cada ruta SIP y cambia cada llamada a
`starting` antes de contactar al proveedor. Esto permite ejecutar varios workers
sin procesar dos veces la misma llamada. Una llamada que permanezca en `starting`
por más de 120 segundos se recupera automáticamente a `requested`.

Los eventos firmados `call.joined` y `call.ended` actualizan la fila a
`in_progress` y a un estado terminal, respectivamente. Como respaldo ante un
webhook perdido, el mismo worker consulta a Ultravox las llamadas
`queued`/`in_progress` después de `VOICE_CALLBACK_RECONCILE_AFTER_SECONDS`
(30 segundos por defecto). Si Ultravox confirma `ended`, la capacidad se libera
automáticamente. `VOICE_CALLBACK_MAX_ACTIVE_SECONDS` (7200 por defecto) evita
un bloqueo indefinido cuando ni el webhook ni la consulta al proveedor permiten
confirmar el cierre. Los eventos tardíos no pueden devolver una llamada terminal
a un estado activo.

El dashboard CRM muestra por separado **Rendimiento de llamadas (Ultravox)** y
**Capacidad de llamadas salientes (SIP)**. La capacidad actual cuenta llamadas
`starting`, `queued`, `ringing` e `in_progress`; los rechazos `call_capacity_reached`, las
reconciliaciones y los cierres máximos se registran de forma sanitizada en
`tenant_integration_events`. Los contadores comienzan con la versión que incorpora
estos eventos: no se reconstruyen rechazos históricos. Los filtros de fuente y
campaña no modifican la capacidad SIP; sólo el período limita sus contadores e
historial. No se requieren migraciones, variables nuevas ni cambios en Asterisk.

Sin el worker, la solicitud queda guardada en `requested`, pero la llamada real
no comienza. En staging continuo, despliegue el worker como un servicio separado
con el mismo código, `DATABASE_URL` y claves de cifrado del backend. No asigne
dominio ni puerto público. Si se usa Nixpacks en Dokploy, configure:

```text
NIXPACKS_START_CMD=python -m app.workers.voice_callback_worker
```

El agente `app.workers.asterisk_provisioner` es otro proceso: corre en el servidor
Asterisk, no usa `DATABASE_URL` y consulta el backend mediante
`SERVIGLOBAL_API_URL` y `ASTERISK_PROVISIONER_SHARED_SECRET`.

7. Valide la configuración antes de recargar y use `pjsip reload` y `dialplan reload`; no reinicie Asterisk. Conserve copia de los includes anteriores para rollback. Las extensiones 1001/1002 usan `from-internal-test`, que rechaza todo hasta que se agreguen números exactos de prueba.
8. Antes de habilitar un tenant, confirme con IDT que su división admite los ocho países y el formato `${IDT_DIVISION}${E164_SIN_MAS}`. Ejecute una llamada controlada por país y verifique audio bidireccional, DTMF, Caller ID, webhook, duración y CRM.

El repositorio contiene Dockerfiles separados para frontend y backend. El despliegue actual usa Dokploy/VPS y puede activarse mediante workflows/webhooks configurados fuera del código. Antes de desplegar:

1. Verifique variables y dominios del entorno.
2. Confirme CORS del backend y `NEXT_PUBLIC_API_URL` del build frontend.
3. Ejecute migraciones una sola vez desde un job controlado.
4. Verifique health/API, login, dashboard y un flujo representativo del canal modificado.
5. Confirme firmas y URLs públicas de webhooks.
6. Si el entorno usa automatizaciones, despliegue y supervise también el proceso `app.workers.notification_worker`; desplegar sólo FastAPI no procesa la cola pendiente.

`NEXT_PUBLIC_API_URL` es build-time: cambiarla exige reconstruir el frontend.

### Migración de Chatwoot a multi-tenant

Chatwoot dejó de configurarse por variables de entorno globales; ahora es una integración por tenant (`TenantChatwootConfig`, migración `202609010001_chatwoot_multitenant_v1.py`). Antes de desplegar este cambio a un entorno que ya usaba el Chatwoot global:

1. Aplique la migración y confirme una sola head de Alembic.
2. Cree manualmente el `TenantChatwootConfig` del tenant que hoy depende del Chatwoot global (`Settings → Integrations → Chatwoot`), copiando los valores que antes vivían en `.env`: URL de la instancia, `account_id`, inbox por defecto y el access token de Chatwoot. No hay migración automática de datos ni fallback en código a los valores anteriores.
3. Pruebe la conexión (`Probar conexión`) y confirme `has_secret: true`.
4. Copie la `webhook_url` mostrada en la tarjeta y configúrela en Chatwoot → Settings → Integrations → Webhooks para esa Account, reemplazando la URL anterior (`/api/v1/chatwoot/webhook`, retirada).
5. Envíe un mensaje entrante real desde esa Account y confirme en `tenant_integration_events` (`provider="chatwoot"`) que se registra `webhook_received` para el tenant correcto.

### Auto-provisioning "managed" (Chatwoot Platform API)

`POST /api/v1/integrations/chatwoot/provision` (`ChatwootPlatformClient`, `backend/app/services/chatwoot_platform_client.py`) crea, vía la Platform API de Chatwoot: una Account (`platform/api/v1/accounts`), un usuario `administrator` dedicado (`platform/api/v1/users` + `platform/api/v1/accounts/{id}/account_users`), un inbox tipo `api` (`api/v1/accounts/{id}/inboxes`) y el webhook de cuenta (`api/v1/accounts/{id}/webhooks`, el mismo mecanismo que "external" configura a mano en Settings → Integrations → Webhooks).

**No usa Agent Bots.** La primera versión sí los usaba y se descartó tras probar contra la instancia real (2026-09-02): un token de Agent Bot devuelve `"Access to this endpoint is not authorized for bots"` para cualquier endpoint de `/api/v1/accounts/*`, incluyendo crear un contacto — es decir, no sirve ni para el aprovisionamiento ni para el uso en runtime que hace `ChatwootClient`. El token que se guarda como `api_token_encrypted` es el del usuario `administrator` creado para la ocasión (mismo tipo de credencial que el operador crea a mano en modo "external").

Validado end-to-end contra `crm.serviglobal-ia.com` el 2026-09-02 (Account, usuario, inbox y webhook creados correctamente; `GET /api/v1/accounts/{id}` y `POST .../contacts` confirmados con el token del usuario). La corrida de validación dejó Accounts de prueba reales, ya suspendidas (`status: suspended` vía `PATCH /platform/api/v1/accounts/{id}`, la Platform API no expone borrado):

- Accounts `id=2` ("ServiGlobal QA Test - DELETE ME") e `id=3` ("ServiGlobal E2E Diagnostic - DELETE ME"), con sus inboxes, webhooks, un contacto de prueba y los usuarios `administrator` asociados.
- Dos Agent Bots huérfanos en la Account `id=2` (del diseño descartado), sin uso ni referencia en el código actual.

Bórrelas a mano (UI de Chatwoot o Rails console) cuando convenga; mientras tanto están suspendidas, no operativas.

## Checklist de seguridad

- No modificar ni confirmar `.env`, `opencode.jsonc` o secretos.
- No registrar Authorization, tokens, API keys, payloads completos, HTML, adjuntos o PII sensible.
- Confirmar que respuestas de configuración exponen `has_secret`, no el secreto.
- Confirmar aislamiento tenant en consultas, archivos y eventos.
- Revisar manualmente coincidencias sensibles con el comando definido en `docs-local/fase-3/agent-rules/SECURITY_AND_LOGGING_RULES.md`.

## Diagnóstico rápido

- CORS: comprobar origen exacto, regex/configuración backend y reconstrucción del frontend si cambió su API pública.
- DB: comprobar `DATABASE_URL`, disponibilidad, `alembic current` y `alembic heads`.
- Integración: usar primero el endpoint de test del tenant y revisar sólo el error sanitizado.
- Notificaciones: comprobar capacidad y regla activas, plantilla Meta `APPROVED`, mapeo completo, `scheduled_for`, estado de la entrega y actividad del worker.
- Playwright de notificaciones: si aparece el login, el `storageState` expiró; regenérelo con `npm.cmd run qa:auth`.
- Webhook: validar URL pública, secreto/firma, status HTTP e idempotencia.
- Assets: comprobar driver, bucket/ruta, permisos y límites de tamaño; el bucket no debe ser público.
