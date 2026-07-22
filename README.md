# ServiGlobal IA

Plataforma multitenant para operar agentes de voz y canales comerciales desde una landing pública, un dashboard privado y un CRM. El repositorio ya no contiene únicamente la landing: integra identidad, analítica, CRM, email, formularios, reservas, WhatsApp, voz y control de consumo por tenant.

## Estado actual

- Landing pública bilingüe (`es`/`en`) con demos inbound WebRTC y outbound/callback.
- Autenticación Auth0, onboarding y administración de tenants, membresías y agentes.
- Dashboard operativo con KPIs, tendencias, distribución, heatmap, llamadas recientes, uso y ahorro estimado.
- CRM multitenant con pipeline, leads, detalle, timeline, notas, tareas, métricas y acciones rápidas.
- Ingesta de llamadas Ultravox con persistencia, normalización, resumen y correlación con leads.
- Email transaccional por tenant mediante Resend, composer Markdown/MDX controlado, adjuntos local/S3 y formularios públicos con tokens opacos.
- Reservas Cal.com: disponibilidad, creación, cancelación, reprogramación y reconciliación por webhook.
- Google Calendar en modo foundation: conexión/desconexión y consulta de conexiones; la inserción directa de eventos sigue deshabilitada.
- WhatsApp Cloud API por tenant: configuración cifrada, plantillas, envío CRM, mensajes y webhook Meta.
- Voz por tenant: proveedor y agentes configurables, llamadas CRM, webhook y herramientas internas de booking protegidas.
- Planes, límites, consumo, alertas y comparación de ahorro por tenant.

La matriz detallada de capacidades y limitaciones está en [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md).

## Arquitectura

```text
Navegador / proveedores
        |
        +-- Next.js 15 (landing, dashboard, CRM, admin)
        |
        +-- FastAPI (API, webhooks, herramientas internas)
                 |
                 +-- PostgreSQL + Alembic
                 +-- Auth0
                 +-- Ultravox / Cal.com / Meta / Resend
                 +-- almacenamiento local o S3 compatible
```

- `frontend/`: Next.js, React, TypeScript, Tailwind, next-intl y Playwright.
- `backend/`: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL y clientes de proveedores.
- `docs/`: documentación canónica vigente.
- `docs-local/`: decisiones y cierres históricos por fase/sprint.

Consulta [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) y [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Ejecución local

Requisitos: Node.js 20+, Python 3.11+ y PostgreSQL 16.

```powershell
docker compose up -d postgres pgadmin

cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

En otra terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Copie únicamente las variables necesarias desde `backend/.env.example` y `frontend/.env.example`. No confirme archivos `.env` ni secretos. La guía completa está en [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Validación

```powershell
cd backend
python -m unittest discover -p "test_*.py"
python -m compileall app
alembic heads

cd ..\frontend
npm.cmd run lint
npx.cmd tsc --noEmit --incremental false
npm.cmd run build

cd ..
git diff --check
```

`alembic heads` debe devolver una sola cabeza. Algunos tests de integración requieren servicios o credenciales de prueba; nunca deben apuntar a producción.

## Documentación

- [Índice documental](docs/README.md)
- [Estado funcional](docs/PROJECT_STATUS.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Referencia de API](docs/API_REFERENCE.md)
- [Configuración, despliegue y operación](docs/OPERATIONS.md)
- [Especificación vigente](SPECS.md)
- [Contenido comercial de la landing](landing_content.md)

## Reglas de contribución

- No trabajar directamente sobre `develop`.
- Mantener aislamiento multitenant; la UI tenant nunca envía `tenant_id`.
- Cifrar secretos por tenant y no exponerlos ni registrarlos en logs.
- No mezclar cambios de WhatsApp y voz en una misma rama de implementación.
- Ejecutar tests, lint, typecheck, build y `git diff --check` antes de entregar.
- Para Sprint 3, leer primero las reglas de `docs-local/fase-3/agent-rules/`.
