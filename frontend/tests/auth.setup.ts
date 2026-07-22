import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

test('guardar sesión Auth0 para QA', async ({ page }) => {
  test.setTimeout(0);
  await page.goto('/es/crm');
  console.log('Completa el login en Chromium y pulsa Resume en Playwright Inspector.');
  await page.pause();
  await expect(page).toHaveURL(/\/es\/crm(?:\/|$)/);
  await mkdir('playwright/.auth', { recursive: true });
  await page.context().storageState({ path: 'playwright/.auth/user.json' });
});
