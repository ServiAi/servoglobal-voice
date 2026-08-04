# Índice de documentación

## Documentos canónicos

- [PROJECT_STATUS.md](PROJECT_STATUS.md): qué está implementado, qué es parcial y qué no está habilitado.
- [ARCHITECTURE.md](ARCHITECTURE.md): componentes, datos, seguridad y flujos principales.
- [API_REFERENCE.md](API_REFERENCE.md): familias de endpoints y reglas de acceso.
- [OPERATIONS.md](OPERATIONS.md): configuración local, migraciones, pruebas y despliegue.
- [../SPECS.md](../SPECS.md): especificación funcional vigente.
- [../landing_content.md](../landing_content.md): inventario editorial/comercial de la landing.

## Historial de implementación

`docs-local/fase-2/` documenta los sprints del CRM y `docs-local/fase-3/` los sprints de integraciones. Son evidencia histórica: si difieren del código o de los documentos canónicos, prevalecen el código actual y `docs/`.

## Punto de continuidad actual

La administración tenant de automatizaciones y notificaciones está disponible en `/[locale]/crm/settings/notifications`. Su estado funcional, arquitectura, endpoints y operación se documentan respectivamente en `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `API_REFERENCE.md` y `OPERATIONS.md`.

Los últimos cambios de UI añadieron ayuda contextual a todos los campos de reglas y cierre automático al hacer clic fuera de la ayuda. El comportamiento compartido vive en `frontend/components/crm/integrations/FieldHelp.tsx`; no debe duplicarse dentro de cada formulario.

## Guías especializadas

- [../backend/WHATSAPP_CHATWOOT_ARCHITECTURE.md](../backend/WHATSAPP_CHATWOOT_ARCHITECTURE.md)
- [../backend/CHATWOOT_DOKPLOY_SETUP.md](../backend/CHATWOOT_DOKPLOY_SETUP.md)
- [../frontend/tests/QA_VISUAL.md](../frontend/tests/QA_VISUAL.md)

## Mantenimiento

Al cerrar una funcionalidad, actualice primero `PROJECT_STATUS.md`; si cambia una ruta o contrato, actualice `API_REFERENCE.md`; si cambia infraestructura o variables, actualice `OPERATIONS.md`; y si cambia un invariante para agentes, actualice `AGENTS.md`. No copie secretos, IDs reales ni datos de clientes a la documentación.
