# Configuración y operación

## Entorno local

1. Levante PostgreSQL con `docker compose up -d postgres`.
2. Cree `backend/.env` y `frontend/.env.local` desde los ejemplos, sin versionarlos.
3. Instale dependencias, ejecute `alembic upgrade head` y arranque FastAPI.
4. Instale dependencias frontend y arranque Next.js.

Variables base:

- Backend: `DATABASE_URL`, `PORT`, Auth0, Ultravox y `INTEGRATIONS_ENCRYPTION_KEY`.
- Frontend: `NEXT_PUBLIC_API_URL`, Auth0 y Turnstile cuando se use la demo pública.
- Integraciones opcionales: Cal.com, Google Calendar, Resend/storage, WhatsApp, Chatwoot y secretos de webhooks/herramientas internas.

Los nombres vigentes y placeholders están en los archivos `.env.example`. Nunca copie valores reales a documentación, logs o commits.

## Base de datos

```powershell
cd backend
alembic heads
alembic upgrade head
alembic current
```

Debe existir una sola head. No ejecute migraciones contra producción desde una sesión local sin autorización explícita y respaldo operativo.

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

Ejecute pruebas focalizadas durante el desarrollo y la suite completa antes de merge. Playwright requiere el entorno definido en su configuración y, según el proyecto, sesión Auth0 preparada.

## Despliegue

El repositorio contiene Dockerfiles separados para frontend y backend. El despliegue actual usa Dokploy/VPS y puede activarse mediante workflows/webhooks configurados fuera del código. Antes de desplegar:

1. Verifique variables y dominios del entorno.
2. Confirme CORS del backend y `NEXT_PUBLIC_API_URL` del build frontend.
3. Ejecute migraciones una sola vez desde un job controlado.
4. Verifique health/API, login, dashboard y un flujo representativo del canal modificado.
5. Confirme firmas y URLs públicas de webhooks.

`NEXT_PUBLIC_API_URL` es build-time: cambiarla exige reconstruir el frontend.

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
- Webhook: validar URL pública, secreto/firma, status HTTP e idempotencia.
- Assets: comprobar driver, bucket/ruta, permisos y límites de tamaño; el bucket no debe ser público.
