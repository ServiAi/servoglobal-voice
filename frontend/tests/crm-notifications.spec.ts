import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { toLocalDayEndIso, toLocalDayStartIso } from '../lib/notifications/date-range';

const PATH = '/es/crm/settings/notifications';

test.describe('helpers de rango de fechas', () => {
  test('un rango de un mismo día cubre el día local completo sin desplazarse', () => {
    const start = toLocalDayStartIso('2026-03-15');
    const end = toLocalDayEndIso('2026-03-15');
    const startMs = new Date(start).getTime();
    const endMs = new Date(end).getTime();

    // El rango de un mismo día debe cubrir 24h menos 1ms, no colapsar en el
    // mismo instante como hacía `new Date('YYYY-MM-DD').toISOString()`.
    expect(endMs - startMs).toBe(24 * 60 * 60 * 1000 - 1);

    const expectedStart = new Date(2026, 2, 15, 0, 0, 0, 0);
    const expectedEnd = new Date(2026, 2, 15, 23, 59, 59, 999);
    expect(startMs).toBe(expectedStart.getTime());
    expect(endMs).toBe(expectedEnd.getTime());
  });
});

test.describe('Automatizaciones y notificaciones', () => {
  test('vista desktop carga sin errores de accesibilidad críticos', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1024 });
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: /Automatizaciones y notificaciones/i })).toBeVisible();
    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });

  test('vista móvil no genera overflow horizontal', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: /Automatizaciones y notificaciones/i })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test('navegación por pestañas con teclado', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    const rulesTab = page.getByRole('tab', { name: /Reglas/i });
    await rulesTab.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('tabpanel', { name: /Automatizaciones/i }).or(page.locator('#notifications-panel-rules'))).toBeVisible();
    await expect(rulesTab).toHaveAttribute('aria-selected', 'true');
  });

  test('estado de solo lectura es consistente cuando no hay permisos de escritura', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const canEdit = await newRuleButton.isVisible().catch(() => false);
    if (!canEdit) {
      await page.getByRole('tab', { name: /Reglas/i }).click();
      await expect(page.getByRole('button', { name: /^Editar$/i })).toHaveCount(0);
    }
  });

  test('togglear una capacidad hace un viaje de ida y vuelta contra el backend', async ({ page }) => {
    // El bearer token ya no viaja al cliente: la mutación corre en un Server
    // Action, así que no se puede interceptar con page.route(); se valida
    // contra el backend real que el estado visual va y vuelve.
    await page.goto(PATH, { waitUntil: 'networkidle' });
    const toggle = page.getByRole('switch').first();
    const isEditable = await toggle.isEnabled().catch(() => false);
    test.skip(!isEditable, 'La sesión de QA no tiene permisos de escritura para automatizaciones.');

    const initial = await toggle.getAttribute('aria-checked');
    await toggle.click();
    await expect(toggle).not.toHaveAttribute('aria-checked', initial ?? 'false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', initial ?? 'false');
  });

  test('el flujo de creación de reglas exige una plantilla aprobada por Meta', async ({ page }) => {
    // La creación depende de un Server Action; sin plantillas sincronizadas y
    // aprobadas por Meta en el tenant de QA, la creación debe permanecer
    // deshabilitada con un estado vacío explícito en vez de aceptar cualquier
    // template_key de texto libre.
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Reglas/i }).click();
    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const canCreate = await newRuleButton.isVisible().catch(() => false);

    if (!canCreate) {
      const canEdit = await page.getByRole('button', { name: /^Editar$/i }).first().isVisible().catch(() => false);
      test.skip(!canEdit, 'La sesión de QA no tiene permisos de escritura para automatizaciones.');
      await expect(page.getByText(/plantillas de WhatsApp aprobadas por Meta/i)).toBeVisible();
      return;
    }

    await newRuleButton.click();
    const templateField = page.getByLabel(/^Plantilla WhatsApp$/i);
    await expect(templateField).toBeVisible();
    await expect(templateField.locator('option')).not.toHaveCount(0);
  });

  test('las condiciones de comparación numérica usan un input numérico', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Reglas/i }).click();
    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const canCreate = await newRuleButton.isVisible().catch(() => false);
    test.skip(!canCreate, 'No hay plantillas aprobadas o permisos de escritura en este entorno de QA.');

    await newRuleButton.click();
    await page.getByLabel(/^Capacidad$/i).selectOption('call_notifications');
    await page.getByLabel(/^Evento$/i).selectOption('call.completed');
    await page.getByRole('button', { name: /Agregar condición/i }).click();

    const fieldSelect = page.locator('select[aria-label="field"]').first();
    await fieldSelect.selectOption('call.duration_seconds');

    const operatorSelect = page.locator('select[aria-label="operator"]').first();
    const valueInput = page.locator('input[aria-label="value"]').first();

    await operatorSelect.selectOption('greater_than');
    await expect(valueInput).toHaveAttribute('type', 'number');

    await valueInput.fill('60');
    await expect(valueInput).toHaveValue('60');

    // El control lo determina el tipo del campo, no el operador.
    await operatorSelect.selectOption('equals');
    await expect(valueInput).toHaveAttribute('type', 'number');

    // Cambiar a un operador sin valor lo elimina del formulario.
    await operatorSelect.selectOption('exists');
    await expect(page.locator('input[aria-label="value"]')).toHaveCount(0);
  });

  test('capacidad y evento cargan el contrato y los datos de prueba dependientes', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Reglas/i }).click();
    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const canCreate = await newRuleButton.isVisible().catch(() => false);
    test.skip(!canCreate, 'No hay plantillas aprobadas o permisos de escritura en este entorno de QA.');

    await newRuleButton.click();
    const eventSelect = page.getByLabel(/^Evento$/i);
    await expect(eventSelect).toBeDisabled();
    await page.getByLabel(/^Capacidad$/i).selectOption('booking_notifications');
    await expect(eventSelect.locator('option[value="booking.created"]')).toHaveCount(1);
    await eventSelect.selectOption('booking.created');
    await expect(page.getByLabel(/Datos del evento para la prueba/i)).toHaveValue(/booking-demo-001/);

    await page.getByRole('button', { name: /Agregar condición/i }).click();
    const fieldSelect = page.locator('select[aria-label="field"]').first();
    await expect(fieldSelect.locator('option[value="booking.status"]')).toHaveCount(1);
    await fieldSelect.selectOption('booking.status');
    await expect(page.locator('select[aria-label="value"]').first()).toBeVisible();
  });

  test('los campos de la regla muestran ayuda contextual al hacer clic', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Reglas/i }).click();

    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const editButton = page.getByRole('button', { name: /^Editar$/i }).first();
    if (await newRuleButton.isVisible().catch(() => false)) {
      await newRuleButton.click();
    } else if (await editButton.isVisible().catch(() => false)) {
      await editButton.click();
    } else {
      test.skip(true, 'La sesión de QA no puede abrir el formulario de reglas.');
    }

    const nameHelp = page.getByLabel(/Ayuda para Nombre/i);
    await expect(nameHelp).toBeVisible();
    await nameHelp.click();
    await expect(page.getByText(/nombre interno, claro y único/i)).toBeVisible();
    await page.getByRole('heading', { name: /Nueva regla|Editar regla/i }).click();
    await expect(page.getByText(/nombre interno, claro y único/i)).toBeHidden();
  });

  test('aplicar filtros de entregas no genera errores', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Entregas/i }).click();

    const applyButton = page.getByRole('button', { name: /Aplicar filtros/i });
    await expect(applyButton).toBeVisible();

    const statusFilter = page.locator('#notifications-panel-deliveries select').first();
    await statusFilter.selectOption('failed');
    await applyButton.click();

    await expect(page.locator('#notifications-panel-deliveries [role="alert"]')).toHaveCount(0);
  });

  test('abrir el detalle de una entrega no expone datos sensibles', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Entregas/i }).click();
    const firstRow = page.locator('#notifications-panel-deliveries table tbody tr').first();
    const hasDeliveries = await firstRow.isVisible().catch(() => false);
    test.skip(!hasDeliveries, 'No hay entregas existentes para inspeccionar en este entorno.');

    await firstRow.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const dialogText = await dialog.innerText();
    expect(dialogText).not.toMatch(/claim_token|payload_json|access_token|webhook_secret/i);
  });
});
