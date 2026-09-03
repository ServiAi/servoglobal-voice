import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const routes = [
  'dashboard',
  'crm',
  'crm/leads',
  'crm/tasks',
  'crm/analytics',
  'voice-ai/experiences',
  'voice-ai/calls',
  'voice-ai/analytics',
  'voice-ai/telephony',
  'crm/settings/integrations',
  'crm/settings/notifications',
];
const locales = ['es', 'en'] as const;
const themes = ['light', 'dark'] as const;
const viewports = [
  { name: '1440x1024', width: 1440, height: 1024 },
  { name: '1280x800', width: 1280, height: 800 },
  { name: '1024x768', width: 1024, height: 768 },
  { name: '768x1024', width: 768, height: 1024 },
  { name: '430x932', width: 430, height: 932 },
  { name: '390x844', width: 390, height: 844 },
  { name: '375x812', width: 375, height: 812 },
  { name: '320x568', width: 320, height: 568 },
] as const;

async function applyTheme(page: Page, theme: (typeof themes)[number]) {
  await page.addInitScript((value) => localStorage.setItem('theme', value), theme);
  await page.emulateMedia({ colorScheme: theme });
}

for (const locale of locales) {
  for (const viewport of viewports) {
    for (const theme of themes) {
      test.describe(`${locale} ${viewport.name} ${theme}`, () => {
        test.use({ viewport: { width: viewport.width, height: viewport.height } });

        for (const route of routes) {
          test(`${route} responde, no desborda y es accesible`, async ({ page }) => {
            const browserErrors: string[] = [];
            page.on('console', (message) => {
              if (message.type() === 'error') browserErrors.push(message.text());
            });
            page.on('pageerror', (error) => browserErrors.push(error.message));

            await applyTheme(page, theme);
            const response = await page.goto(`/${locale}/${route}`, { waitUntil: 'domcontentloaded' });
            expect(response?.ok(), `HTTP ${response?.status()} en /${locale}/${route}`).toBeTruthy();
            await expect(page).toHaveURL(new RegExp(`/${locale}/${route.replace('/', '\\/')}(?:[/?#]|$)`));
            await expect(page.locator('body')).toBeVisible();
            await expect(page.locator('html')).toHaveAttribute('lang', new RegExp(`^${locale}(?:-|$)`, 'i'));

            if (route === 'voice-ai/analytics') {
              await expect(page.getByRole('heading', { name: locale === 'en' ? 'Call performance (Ultravox)' : 'Rendimiento de llamadas (Ultravox)' })).toBeVisible();
            }
            if (route === 'voice-ai/telephony') {
              await expect(page.getByRole('heading', { name: locale === 'en' ? 'Outbound call capacity (SIP)' : 'Capacidad de llamadas salientes (SIP)' })).toBeVisible();
            }

            const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
            expect(overflow, 'La página tiene overflow horizontal global').toBeLessThanOrEqual(1);

            const accessibility = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze();
            expect(accessibility.violations, JSON.stringify(accessibility.violations, null, 2)).toEqual([]);
            expect(browserErrors, browserErrors.join('\n')).toEqual([]);
            // The tenant app (dashboard, CRM, etc.) is a standalone tool and
            // must never show the ServiGlobal marketing footer.
            await expect(page.locator('footer')).toHaveCount(0);
            if (process.env.QA_VISUAL_SNAPSHOTS === 'true') {
              await expect(page).toHaveScreenshot(`${locale}-${route.replaceAll('/', '-')}-${viewport.name}-${theme}.png`, { fullPage: true });
            }
          });
        }
      });
    }
  }
}
