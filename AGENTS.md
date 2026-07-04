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
