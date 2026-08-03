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

- No trabajar directamente sobre `develop`.
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
