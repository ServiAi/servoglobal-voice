import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

for (const locale of ['es', 'en'] as const) {
  test(`${locale} Ultravox administration keeps link and import distinct`, async ({ page }) => {
    await page.goto(`/${locale}/integrations/voice`);

    const agentsLabel = locale === 'es' ? 'Agentes' : 'Agents';
    await page.getByRole('tab', { name: agentsLabel }).click();
    await expect(page.getByRole('heading', {
      name: locale === 'es' ? 'Agentes administrados por Ultravox' : 'Ultravox-managed agents',
    })).toBeVisible();
    await expect(page.getByText(
      locale === 'es'
        ? 'Vincular conserva Ultravox como fuente de verdad. Importar crea un draft independiente.'
        : 'Linking keeps Ultravox as the source of truth. Importing creates an independent draft.'
    )).toBeVisible();

    await page.getByRole('tab', { name: locale === 'es' ? 'Voces' : 'Voices' }).click();
    await expect(page.getByText(
      locale === 'es'
        ? 'Capabilities normalizadas por ServiGlobal; la definición remota no se expone.'
        : 'Capabilities are normalized by ServiGlobal; the remote definition is never exposed.'
    )).toBeVisible();

    const accessibility = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });
}
