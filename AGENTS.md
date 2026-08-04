"Este proyecto tiene mcp CodeGraph inicializado"

Reglas Estrictas:

Usa codegraph_explore como tu herramienta PRINCIPAL para cualquier tarea de exploracion.

NO vuelvas a leer archivos para los cuales codegraph_explore ya devolvio codigo fuente. Los fragmentos fuente son completos y autoritativos.

Solo recurre a grep/glob/read para archivos listados bajo 'Archivos relevantes adicionales' si necesitas mas detalle, o si codegraph no arrojo resultados.

<!-- BEGIN PONYTAIL DEFAULT -->
# Ponytail Default Mode

Actua como un senior developer perezoso en el buen sentido: eficiente, no descuidado. Para cualquier tarea de codigo, aplica por defecto este orden:

1. Si no necesita existir, no lo construyas; dilo brevemente.
2. Si la standard library lo resuelve, usala.
3. Si la plataforma nativa lo resuelve, usala antes que una dependencia.
4. Si ya hay una dependencia instalada que lo resuelve, usala antes de crear otra abstraccion.
5. Si puede ser una linea clara y correcta, hazlo en una linea.
6. Solo entonces implementa el minimo codigo que funciona.

Evita abstracciones no pedidas, factories de una sola implementacion, capas especulativas, boilerplate y dependencias nuevas innecesarias. Prefiere borrar a agregar. Manten el diff pequeno.

No recortes: validacion en fronteras de confianza, seguridad, manejo de errores que evite perdida de datos, accesibilidad, tests minimos para logica no trivial, ni nada que el usuario pidio explicitamente.

Si el usuario dice "normal mode" o "stop ponytail", deja de aplicar Ponytail en esa conversacion.
<!-- END PONYTAIL DEFAULT -->

<!-- BEGIN MULTI-TOOL SKILLS -->
# Skills instaladas - Regla universal para cualquier herramienta agentica

Este proyecto tiene skills instaladas que DEBEN usarse sin importar que herramienta agentica este operando (Claude Code, Codex, Antigravity, OpenCode, Cursor, Gemini CLI, GitHub Copilot, etc). El nombre de la herramienta no cambia la regla: el comportamiento esperado es el mismo en todas.

Reglas obligatorias por tipo de tarea:

1. **Cualquier tarea de codigo** (escribir, editar, refactorizar, corregir bugs): aplica por defecto la skill `ponytail` (ver "Ponytail Default Mode" arriba).
2. **Cualquier tarea de exploracion** (entender el codebase, buscar simbolos, mapear dependencias): usa `codegraph` / `codegraph_explore` como herramienta principal (ver reglas al inicio de este archivo).
3. **Tareas de UI/frontend** (componentes, estilos, layout, diseno visual): usa la skill `frontend-design` si esta disponible para la herramienta activa.
4. Para cualquier otra skill instalada, revisa la carpeta correspondiente antes de asumir que no existe.

## Como localizar las skills segun la herramienta activa

Cada herramienta agentica lee las skills desde una carpeta distinta en la raiz del repo. Antes de decir "no tengo esa skill", el agente debe verificar la carpeta que le corresponde:

| Herramienta agentica | Carpeta de skills a verificar |
|---|---|
| Claude Code | `.claude/skills/` (normalmente symlinks hacia `.agents/skills/`) |
| Antigravity | `.agents/skills/` |
| Codex | `.agents/skills/` |
| OpenCode | `.agents/skills/` |
| Cursor | `.agents/skills/` |
| Gemini CLI | `.agents/skills/` |
| GitHub Copilot | `.agents/skills/` |

`.agents/skills/` es la carpeta universal/canonica donde se instalan las skills (via `npx skills add`); `.claude/skills/` normalmente solo contiene symlinks hacia esa carpeta universal para que Claude Code las reconozca. Si una herramienta no encuentra la skill en su carpeta esperada, revisa tambien `.agents/skills/` antes de concluir que la skill no esta disponible.

Skills instaladas actualmente en `.agents/skills/`: `frontend-design`, `ponytail`, `claude-api`, `vercel-react-best-practices`, `web-artifacts-builder`. Esta lista puede crecer; si no reconoces el nombre de una skill que el usuario menciona, lista el contenido de la carpeta correspondiente antes de responder que no existe.
<!-- END MULTI-TOOL SKILLS -->

# Sprint 3 - Reglas obligatorias para agentes IA

Antes de implementar cualquier tarea del Sprint 3, todo agente debe leer y respetar estos documentos:

- `docs-local/fase-3/agent-rules/SPRINT_3_GLOBAL_RULES.md`
- `docs-local/fase-3/agent-rules/BRANCHING_AND_MERGE_RULES.md`
- `docs-local/fase-3/agent-rules/SECURITY_AND_LOGGING_RULES.md`

Si el agente trabaja en WhatsApp, tambien debe leer:

- `docs-local/fase-3/agent-rules/CODEX_WHATSAPP_RULES.md`

Si el agente trabaja en Voz, tambien debe leer:

- `docs-local/fase-3/agent-rules/ANTIGRAVITY_VOICE_RULES.md`

## Reglas criticas Sprint 3

- No trabajar directamente sobre `develop`, salvo autorización explícita del usuario para la tarea actual. Verifique la rama y el estado antes de editar.
- No modificar `.env`.
- No modificar `opencode.jsonc`.
- No modificar secretos.
- No tocar produccion.
- No romper Auth0.
- No romper Resend.
- No romper Email Composer.
- No romper MinIO/S3.
- No romper Cal.com.
- No romper Google Calendar foundation.
- No romper voice booking tools.
- No mezclar WhatsApp y Voz en la misma rama.
- No aceptar `tenant_id` desde frontend tenant.
- No permitir `tenant_id` arbitrario desde endpoints internos.
- No loguear tokens, API keys, Authorization headers, payloads completos ni PII sensible.
- Antes de entregar cambios, ejecutar tests, lint, typecheck, build y `git diff --check`.

# Documentación canónica y continuidad

- La documentación vigente está en `docs/README.md`, `docs/PROJECT_STATUS.md`, `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md` y `docs/OPERATIONS.md`.
- `docs-local/` conserva evidencia histórica. Si contradice al código o a `docs/`, prevalecen el código actual y `docs/`.
- Al terminar una funcionalidad, actualice `PROJECT_STATUS.md`; actualice también API, arquitectura u operaciones sólo cuando cambien contratos, flujos, infraestructura o comandos.
- No documente secretos, credenciales, IDs reales, teléfonos, correos, payloads completos ni datos de clientes.

# Estado actual: automatizaciones y notificaciones

Base revisada en `develop`: `dbcdc8e` (2026-08-04).

## Mapa del frontend

- Ruta: `frontend/app/[locale]/crm/settings/notifications/page.tsx`.
- Contenedor: `frontend/components/crm/notifications/NotificationsWorkspace.tsx`.
- Paneles: `RulesPanel.tsx`, `RecipientsPanel.tsx` y `DeliveriesPanel.tsx`.
- Cliente tipado: `frontend/lib/api/notification-admin.ts`.
- Mutaciones: Server Actions en `frontend/app/[locale]/crm/settings/notifications/actions.ts`; no vuelva a enviar el bearer token desde componentes cliente.
- Traducciones: mantener paridad entre `frontend/messages/es.json` y `frontend/messages/en.json`.

## Invariantes de UI

- La creación de reglas requiere una plantilla WhatsApp activa, sincronizada desde Meta y `APPROVED`; no reintroducir `template_key` libre.
- Cada campo del formulario de reglas debe conservar su ayuda contextual mediante `FieldHelp`; no crear otro tooltip ni añadir una dependencia.
- Una ayuda se abre desde el ícono, se cierra al pulsarlo nuevamente y se cierra con cualquier clic externo. Mantener teclado, foco y `aria-label`.
- Los diálogos largos usan encabezado, cuerpo desplazable y footer en filas separadas. No colocar un footer sticky dentro del cuerpo ni quitar `minmax(0,1fr)`/`min-h-0`.
- Condiciones numéricas usan inputs numéricos; operadores sin valor eliminan `condition.value`.
- Destinos y destinatarios siempre se muestran enmascarados.

## Invariantes backend

- Router: `/api/v1/admin/notifications`; pese al nombre, toda operación sobre recursos deriva el tenant de `AuthContext`. El catálogo común también exige autenticación y ningún endpoint acepta `tenant_id` del frontend.
- Lectura: `platform_admin`, `tenant_admin`, `tenant_analyst`, `tenant_viewer`. Escritura: `platform_admin`, `tenant_admin`.
- Persistencia: `tenant_capabilities`, `tenant_notification_rules`, `tenant_notification_recipients`, `domain_events`, `notification_deliveries`.
- El worker `python -m app.workers.notification_worker` requiere PostgreSQL y procesa claims con lease, reintentos y recuperación. FastAPI por sí solo no drena la cola.
- No exponer en UI o API segura payloads internos, claim tokens, secretos ni destinos completos.

## Validación mínima para continuar

```powershell
cd backend
python -m unittest test_notification_admin test_notification_models test_notification_orchestrator test_notification_event_pipeline test_notification_delivery_claim_service test_notification_delivery_recovery test_notification_retry_policy test_notification_schedule_reconciliation test_notification_worker test_whatsapp_notification_executor
python -m compileall app

cd ..\frontend
npm.cmd run lint
npx.cmd tsc --noEmit --incremental false
npm.cmd run build
npx.cmd playwright test tests/crm-notifications.spec.ts --project=crm-visual

cd ..
git diff --check
```

Playwright requiere `frontend/playwright/.auth/user.json`. Si redirige al login, renueve la sesión con `npm.cmd run qa:auth`; no cambie Auth0 para hacer pasar la prueba.

`test_notification_worker_postgres` es una prueba de integración separada: ejecútela sólo con `DATABASE_URL` apuntando a una instancia PostgreSQL de pruebas disponible.
