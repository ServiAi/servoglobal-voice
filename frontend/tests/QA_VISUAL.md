# QA visual autenticado

## 1. Guardar una sesión de QA

```powershell
npm run qa:auth
```

Completa el login Auth0 en Chromium. Cuando el CRM esté visible, pulsa **Resume** en Playwright Inspector. La sesión se guarda en `playwright/.auth/user.json`, ignorado por Git. Usa exclusivamente una cuenta de QA sin datos productivos.

## 2. Crear las capturas base

```powershell
$env:QA_VISUAL_SNAPSHOTS='true'
npm run qa:visual:update
```

Las capturas son opt-in porque pueden contener información real. Úsalas solo con datos anonimizados; revisa y versiona únicamente las aprobadas. La matriz cubre locales `es` y `en`, temas claro y oscuro, y ocho viewports entre 1440 y 320 px.

## 3. Ejecutar regresión visual

```powershell
npm run qa:visual
npm run qa:report
```

Cada ruta valida respuesta autenticada, locale del documento, overflow horizontal, errores de consola, WCAG mediante axe y comparación de captura.

Para probar un despliegue existente sin iniciar Next localmente:

```powershell
$env:PLAYWRIGHT_BASE_URL='https://qa.example.com'
npm run qa:visual
```

El detalle dinámico `/[locale]/crm/leads/[leadId]` debe añadirse cuando exista un identificador estable de fixture QA.
