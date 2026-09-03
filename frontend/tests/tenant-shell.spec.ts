import { expect, test } from '@playwright/test';

for (const locale of ['es', 'en'] as const) {
  test(`${locale} /dashboard is the real tenant home and does not redirect to /crm`, async ({ page }) => {
    const response = await page.goto(`/${locale}/dashboard`, { waitUntil: 'domcontentloaded' });
    expect(response?.ok()).toBeTruthy();
    await expect(page).toHaveURL(new RegExp(`/${locale}/dashboard(?:[/?#]|$)`));
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(locale === 'en' ? 'Home' : 'Inicio');
  });

  test(`${locale} legacy routes redirect to their new locations`, async ({ page }) => {
    await page.goto(`/${locale}/crm/dashboard`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new RegExp(`/${locale}/crm/analytics(?:[/?#]|$)`));

    await page.goto(`/${locale}/crm/settings/integrations`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new RegExp(`/${locale}/integrations(?:[/?#]|$)`));

    await page.goto(`/${locale}/crm/settings/integrations/whatsapp`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new RegExp(`/${locale}/integrations/whatsapp(?:[/?#]|$)`));

    await page.goto(`/${locale}/crm/settings/notifications`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new RegExp(`/${locale}/automations/notifications(?:[/?#]|$)`));

    await page.goto(`/${locale}/crm/settings/voice-experiences`, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(new RegExp(`/${locale}/voice-ai/experiences(?:[/?#]|$)`));
  });

  test(`${locale} sidebar shows the domain groups and marks the active link`, async ({ page }) => {
    await page.goto(`/${locale}/crm/leads`, { waitUntil: 'domcontentloaded' });
    const nav = page.getByRole('navigation', { name: locale === 'en' ? 'Main CRM navigation' : 'Navegación principal del CRM' });

    const groups = locale === 'en'
      ? ['Home', 'CRM', 'Voice AI', 'Automation', 'Integrations']
      : ['Inicio', 'CRM', 'Voz IA', 'Automatización', 'Integraciones'];
    for (const group of groups) {
      await expect(nav.getByText(group, { exact: true })).toBeVisible();
    }

    await expect(nav.getByRole('link', { name: 'Leads', exact: true })).toHaveAttribute('aria-current', 'page');
  });

  test(`${locale} CRM analytics no longer shows call performance or SIP capacity`, async ({ page }) => {
    await page.goto(`/${locale}/crm/analytics`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: locale === 'en' ? 'Call performance (Ultravox)' : 'Rendimiento de llamadas (Ultravox)' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: locale === 'en' ? 'Outbound call capacity (SIP)' : 'Capacidad de llamadas salientes (SIP)' })).toHaveCount(0);
  });

  test(`${locale} Voz IA telephony shows SIP capacity`, async ({ page }) => {
    await page.goto(`/${locale}/voice-ai/telephony`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: locale === 'en' ? 'Outbound call capacity (SIP)' : 'Capacidad de llamadas salientes (SIP)' })).toBeVisible();
  });
}
