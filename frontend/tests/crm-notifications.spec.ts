import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const PATH = '/es/crm/settings/notifications';

test.describe('Automatizaciones y notificaciones', () => {
  test('vista desktop carga sin errores de accesibilidad críticos', async ({ page }) => {
    test.use({ viewport: { width: 1440, height: 1024 } });
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: /Automatizaciones y notificaciones/i })).toBeVisible();
    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });

  test('vista móvil no genera overflow horizontal', async ({ page }) => {
    test.use({ viewport: { width: 390, height: 844 } });
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

  test('togglear una capacidad actualiza su estado visual', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    const toggle = page.getByRole('switch').first();
    const isEditable = await toggle.isEnabled().catch(() => false);
    test.skip(!isEditable, 'La sesión de QA no tiene permisos de escritura para automatizaciones.');

    const nextEnabled = (await toggle.getAttribute('aria-checked')) !== 'true';
    await page.route('**/api/v1/admin/notifications/capabilities/**', async (route) => {
      const request = route.request();
      const body = request.postDataJSON() as { enabled: boolean };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          capability_key: 'booking_notifications',
          enabled: body.enabled,
          config_json: {},
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked', String(nextEnabled));
  });

  test('crear una regla nueva agrega la fila a la tabla', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Reglas/i }).click();
    const newRuleButton = page.getByRole('button', { name: /Nueva regla/i });
    const canEdit = await newRuleButton.isVisible().catch(() => false);
    test.skip(!canEdit, 'La sesión de QA no tiene permisos de escritura para automatizaciones.');

    await page.route('**/api/v1/admin/notifications/rules', async (route) => {
      if (route.request().method() !== 'POST') return route.continue();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'qa-rule-1',
          name: 'Regla QA Playwright',
          capability_key: 'booking_notifications',
          event_type: 'booking.created',
          channel: 'whatsapp',
          action_type: 'send_whatsapp_template',
          template_key: 'booking_confirmation',
          recipient_strategy: 'event_customer',
          recipient_group_key: null,
          conditions_json: [],
          variable_mapping_json: {},
          schedule_mode: 'immediate',
          schedule_offset_minutes: 0,
          priority: 100,
          enabled: true,
          configuration_error: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    await newRuleButton.click();
    await page.getByLabel(/^Nombre$/i).fill('Regla QA Playwright');
    await page.getByLabel(/^Capacidad$/i).selectOption('booking_notifications');
    await page.getByLabel(/^Evento$/i).selectOption('booking.created');
    const templateField = page.getByLabel(/^Plantilla/i);
    if ((await templateField.evaluate((el) => el.tagName)) === 'SELECT') {
      await templateField.selectOption({ index: 1 }).catch(() => templateField.fill('booking_confirmation'));
    } else {
      await templateField.fill('booking_confirmation');
    }
    await page.getByRole('button', { name: /^Guardar$/i }).click();

    await expect(page.getByText('Regla QA Playwright')).toBeVisible();
  });

  test('filtrar entregas por estado actualiza la tabla', async ({ page }) => {
    await page.goto(PATH, { waitUntil: 'networkidle' });
    await page.getByRole('tab', { name: /Entregas/i }).click();

    await page.route('**/api/v1/admin/notifications/deliveries?*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], page: 1, page_size: 25, total: 0, pages: 0 }),
      });
    });

    const statusFilter = page.locator('#notifications-panel-deliveries select').first();
    await statusFilter.selectOption('failed');
    await expect(page.getByText(/No hay entregas para los filtros seleccionados\./i)).toBeVisible();
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
