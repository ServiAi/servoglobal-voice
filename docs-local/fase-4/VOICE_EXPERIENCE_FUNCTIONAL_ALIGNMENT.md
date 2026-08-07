# Voice Experience — Alineación funcional (Etapa 0)

Rama: `fix/voice-experience-functional-alignment` (base `develop`).

## 1. Objetivo

Corregir inconsistencias funcionales, semánticas, de seguridad y de dominio de Voice Experiences **antes** de construir `feature/voice-experience-public-runtime`. Esta etapa no implementa runtime público: solo alinea el sistema con lo que realmente existe hoy y cierra riesgos.

## 2. Tres conceptos distintos

1. **Demo pública heredada** — `POST /api/v1/calls` y `POST /api/v1/call-outbound`. Es la demo de la landing, resuelta contra el tenant bootstrap. No pertenece a Voice Experiences y no debe conectarse con `TenantVoiceExperience`.
2. **Builder administrativo privado** — Voice Experiences (`/api/v1/voice/experiences`, `/api/v1/voice/context-schemas`). Autenticado y tenant-scoped. "Preparar versión" crea un snapshot interno inmutable. **No** genera URL pública, formulario público, context submission, WebRTC ni llamada.
3. **Futuro runtime público** — `feature/voice-experience-public-runtime` (todavía no iniciado). Será el consumo público tenant-scoped de una versión preparada.

## 3. Semántica temporal de "Versión preparada"

El estado persistido en base de datos sigue siendo `published` (no se renombró). En la interfaz se presenta como **"Versión preparada"** / **"Version prepared"**, y las acciones como **"Preparar versión" / "Retirar versión"**. La UI muestra un aviso permanente: *"Administración privada. No existe enlace público ni runtime de llamada en esta etapa."* No hay "Copiar enlace", URL pública, "Abrir experiencia pública" ni "Probar llamada".

## 4. Política de collection modes

Fuente única: `frontend/lib/voice-experiences/collection-modes.ts` → `getPreCallVisibleContextFields(fields)` (ordena por `position`).

| Modo | Formulario previo |
| --- | --- |
| `ask_if_missing` | Visible |
| `prefill_and_confirm` | Visible |
| `trust_prefill` | Visible |
| `internal_only` | Oculto |
| `collect_during_call` | Oculto (recolección en llamada aún no implementada) |

El futuro runtime público debe reutilizar exactamente esta política.

## 5. Resolución de la versión publicada (fail-closed)

`VoiceExperienceService.get_current_published_version()`:

1. Carga la experiencia por `tenant_id` + `experience_id`.
2. Si `status != "published"` → `None`.
3. Si `published_version_id is None` → `None`.
4. Consulta la versión exacta validando `id == published_version_id`, `experience_id`, `tenant_id`.
5. Referencia inconsistente (otra experiencia u otro tenant) → `None`. Nunca cae a "última versión por número".

## 6. Regla de cambio de agente

`update_experience()` rechaza con **HTTP 409** cambiar `agent_config_id` cuando existe al menos una versión publicada histórica (`Voice experience agent cannot change after publication history exists.`). Cambiar contenido o cambiar de schema dentro del mismo agente sigue permitido. El schema debe seguir perteneciendo al agente y al tenant.

## 7. Conservación del historial

`delete_experience()` solo elimina físicamente cuando la experiencia está **archivada y sin versiones**. Archivada con historial → **HTTP 409** (`Voice experience with publication history cannot be deleted.`), sin borrar experiencia ni snapshots. No se introdujo soft delete ni política de retención completa en esta etapa. La UI oculta/deshabilita "Eliminar" cuando existen versiones.

Un context schema archivado solo puede eliminarse cuando ninguna experiencia actual ni ningún snapshot histórico lo referencia. Eliminar un context schema **nunca** elimina una Voice Experience ni su historial de publicación. Los schemas usados por snapshots forman parte del contrato reproducible de cada publicación y responden **HTTP 409** aunque el borrador actual ya use otro schema. La política de retención completa puede evolucionar posteriormente; la Etapa 0 conserva todo el historial existente.

## 8. Endpoint heredado `/api/v1/calls`

- Contrato tipado con `extra="forbid"`.
- Se eliminaron `system_prompt` y `agent_id` del contrato público (el agente se resuelve server-side vía `DEFAULT_AGENT_ID`).
- `template_context` es un modelo tipado (`DemoCallContext`) con allowlist de las claves que envía la landing (`user_name`, `user_email`, `user_phone`, `user_company`, `user_industry`, `user_use_case`, `user_volume`, `user_pain_point`), normalización y límite de longitud.
- Errores inesperados: se registra un error sanitizado y se responde un mensaje genérico (no `str(exception)`).
- Se conservan Turnstile y los límites de uso del tenant bootstrap.
- Único consumidor real: `frontend/hooks/useUltravox.ts` (envía `template_context` + `turnstile_token`). `DemoInbound.tsx` alimenta esas claves.

**Fuera de alcance:** `POST /api/v1/call-outbound` (usado por `DemoOutbound.tsx`) todavía acepta `agent_id` y no tiene `extra="forbid"`. Se endurecerá en un incremento posterior.

## 9. Limitaciones vigentes

- No existe página pública, formulario público, context submission, WebRTC, `joinUrl` ni llamada asociada a una Voice Experience.
- La recolección "durante la llamada" (`collect_during_call`) no está implementada.
- La vista previa es administrativa y no funcional (100% local).
- No hay soft delete ni retención formal de experiencias.
- `/api/v1/call-outbound` no se endureció en esta etapa.

## 10. Riesgos corregidos

- Una experiencia despublicada ya no resuelve como publicada.
- No se puede cambiar el agente por API después de existir historial.
- No se puede eliminar una experiencia con historial publicado.
- La UI ya no promete una URL pública inexistente.
- El inventario ya no permite preparar versiones a ciegas (422 opacos).
- La demo pública ya no acepta prompts ni provider agent IDs arbitrarios, ni filtra excepciones internas.

## 11. Comandos de validación

```powershell
cd backend
python -m unittest test_voice_experiences test_voice_calls_endpoint test_voice_service_metadata
python -m compileall app
alembic heads   # una sola head: 202608050003 (sin migración nueva)

cd ..\frontend
npm.cmd run lint
npx.cmd tsc --noEmit --incremental false
npx.cmd playwright test tests/voice-experiences.spec.ts --project=crm-visual

cd ..
git diff --check
git status --short
```

Las pruebas puras (`--grep "protecciones puras"`) no requieren app ni sesión Auth0. El resto de la suite E2E requiere `frontend/playwright/.auth/user.json` y la app corriendo.

## 12. Próximo incremento

`feature/voice-experience-public-runtime`: runtime público tenant-scoped que consumirá la versión preparada (formulario público, context submission, WebRTC/`joinUrl`), reutilizando `getPreCallVisibleContextFields` y `get_current_published_version`. No debe reutilizar `/api/v1/calls`.
