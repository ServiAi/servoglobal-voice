# Sprint 6 - Cierre tecnico dashboard privado

## Alcance validado

- Hardening de CORS para el backend privado con allowlist configurable.
- Confirmacion de que el frontend staging consume `https://api-staging.serviglobal-ia.com`.
- Limpieza de warnings triviales de lint en graficos del dashboard.
- Manejo controlado de fallos de red o respuestas invalidas en fetch server-side del dashboard.
- Revision de estados controlados para KPIs, graficos, heatmap y tabla de llamadas recientes.

## Listo para review final

- Login y logout Auth0 en staging.
- Dashboard privado con datos reales del tenant autorizado.
- Filtros por fecha, agente y estado.
- Paginacion de llamadas recientes.
- KPIs, tendencias, distribuciones y heatmap.
- Tenant isolation impuesto en backend por contexto autenticado.

## Pendientes operativos

- Mantener `CORS_ORIGINS` explicito por ambiente antes de promover cambios a otros entornos.
- No promover a produccion sin configurar una allowlist propia para el dominio productivo.
- Auditoria funcional mas granular de consultas puede ampliarse en Fase III.
