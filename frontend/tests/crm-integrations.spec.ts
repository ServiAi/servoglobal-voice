import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

for (const locale of ['es', 'en'] as const) {
  test(`${locale} integration catalog filters and reaches WhatsApp templates in two clicks`, async ({ page }) => {
    await page.goto(`/${locale}/crm/settings/integrations`);

    const search = page.getByRole('searchbox', { name: locale === 'es' ? 'Buscar una integración' : 'Search integrations' });
    await expect(search).toBeVisible();
    await search.fill('term-that-does-not-exist');
    await expect(page.getByRole('heading', { name: /term-that-does-not-exist/ })).toBeVisible();
    await search.fill('whatsapp');
    await page.getByRole('link', { name: new RegExp(`^(Administrar|Configurar|Revisar|Manage|Configure|Review): WhatsApp$`) }).click();
    await expect(page).toHaveURL(new RegExp(`/${locale}/crm/settings/integrations/whatsapp$`));
    await page.getByRole('link', { name: 'Templates', exact: true }).first().click();
    await expect(page).toHaveURL(new RegExp(`/${locale}/crm/settings/integrations/whatsapp/templates$`));

    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
    expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
  });
}
