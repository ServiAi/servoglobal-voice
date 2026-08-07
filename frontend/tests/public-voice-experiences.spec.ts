import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { resolve } from 'node:path';

import type { PublicVoiceExperience as PublicVoiceExperienceData } from '../types/public-voice-experiences';

const experience: PublicVoiceExperienceData = {
  slug: 'consultation-demo',
  locale: 'en',
  version: 3,
  content: {
    title: 'Plan your consultation',
    description: 'Review the information requested before your conversation.',
    submit_label: 'Continue',
    call_label: 'Start call',
    success_message: 'Ready',
  },
  theme: {
    logo_url: 'https://cdn.example.com/logo.svg',
    primary_color: '#0f766e',
    layout: 'split',
  },
  consent: {
    required: true,
    label: 'I accept the data policy.',
    privacy_url: 'https://example.com/privacy',
  },
  fields: [
    {
      key: 'full_name',
      label: 'Full name',
      description: 'How should we address you?',
      field_type: 'text',
      required: true,
      options: [],
    },
    {
      key: 'property_type',
      label: 'Property type',
      description: null,
      field_type: 'select',
      required: false,
      options: [
        { value: 'house', label: 'House' },
        { value: 'apartment', label: 'Apartment' },
      ],
    },
    { key: 'notes', label: 'Notes', description: null, field_type: 'textarea', required: false, options: [] },
    { key: 'email', label: 'Email', description: null, field_type: 'email', required: false, options: [] },
    { key: 'phone', label: 'Phone', description: null, field_type: 'phone', required: false, options: [] },
    { key: 'guests', label: 'Guests', description: null, field_type: 'integer', required: false, options: [] },
    { key: 'verified', label: 'Verified', description: 'I confirm', field_type: 'checkbox', required: false, options: [] },
    { key: 'date', label: 'Date', description: null, field_type: 'date', required: false, options: [] },
  ],
  capabilities: { submissions: false, calls: false },
};

const unsafeExperience: PublicVoiceExperienceData = {
  ...experience,
  slug: 'unsafe-urls',
  theme: { ...experience.theme, logo_url: 'javascript:alert(1)' },
  consent: { ...experience.consent, privacy_url: 'http://example.com/privacy' },
};

let apiServer: Server;

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    if (request.url?.endsWith('/missing')) {
      response.writeHead(404, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({ detail: 'Not found' }));
      return;
    }
    const data = request.url?.endsWith('/unsafe-urls') ? unsafeExperience : experience;
    response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    response.end(JSON.stringify(data));
  });
  await new Promise<void>((resolveListen) => apiServer.listen(43119, '127.0.0.1', resolveListen));
});

test.afterAll(async () => {
  apiServer.closeAllConnections();
  await new Promise<void>((resolveClose, reject) =>
    apiServer.close((error) => (error ? reject(error) : resolveClose())),
  );
});

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => flattenKeys(child, prefix ? `${prefix}.${key}` : key));
}

test('renders the published snapshot as a disabled, responsive public view', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/en/voice/consultation-demo');

  await expect(page.getByRole('heading', { name: experience.content.title })).toBeVisible();
  await expect(page.getByText('Version 3')).toBeVisible();
  await expect(page.getByLabel('Full name')).toBeDisabled();
  await expect(page.getByLabel('Property type')).toBeDisabled();
  for (const label of ['Notes', 'Email', 'Phone', 'Guests', 'Verified', 'Date']) {
    await expect(page.getByLabel(label)).toBeDisabled();
  }
  await expect(page.getByRole('option', { name: 'House' })).toHaveAttribute('value', 'house');
  await expect(page.getByRole('button', { name: 'Continue' })).toBeDisabled();
  await expect(page.getByText('Data capture and calls are not enabled on this page yet.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'View privacy policy' })).toHaveAttribute('href', experience.consent.privacy_url!);
  await expect(page.getByAltText('Experience logo')).toHaveAttribute('src', experience.theme.logo_url!);
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', /noindex/);
  await expect(page.getByTestId('public-voice-runtime').locator('section')).toHaveClass(/lg:grid-cols/);
  expect(await page.locator('header').evaluate((element) => getComputedStyle(element).backgroundColor)).not.toBe('rgba(0, 0, 0, 0)');

  const bodyText = await page.locator('body').innerText();
  expect(bodyText).not.toMatch(/tenant_id|agent_config_id|context_schema_id|system_prompt|api[_-]?key|joinUrl/i);

  const dimensions = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, viewport: window.innerWidth }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);

  const accessibility = await new AxeBuilder({ page })
    .include('[data-testid="public-voice-runtime"]')
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  expect(accessibility.violations).toEqual([]);
});

test('drops unsafe tenant URLs instead of rendering them', async ({ page }) => {
  await page.goto('/en/voice/unsafe-urls');

  await expect(page.getByRole('heading', { name: experience.content.title })).toBeVisible();
  await expect(page.getByAltText('Experience logo')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'View privacy policy' })).toHaveCount(0);
});

test('renders the neutral public not-found state', async ({ page }) => {
  await page.goto('/en/voice/missing');
  await expect(page.getByRole('heading', { name: 'Experience unavailable' })).toBeVisible();
  await expect(page.getByText('We could not find a published experience at this address.')).toBeVisible();
});

test('keeps the public client server-only, unauthenticated, and uncached', () => {
  const client = readFileSync(resolve(process.cwd(), 'lib/api/public-voice-experiences.ts'), 'utf8');
  const page = readFileSync(resolve(process.cwd(), 'app/[locale]/voice/[slug]/page.tsx'), 'utf8');
  const component = readFileSync(resolve(process.cwd(), 'components/public/voice/PublicVoiceExperience.tsx'), 'utf8');

  expect(client).toContain("import 'server-only'");
  expect(client).toContain('/api/v1/public/voice-experiences/');
  expect(client).toContain("cache: 'no-store'");
  expect(client).not.toMatch(/Authorization|getAccessToken|Auth0/i);
  expect(page).toContain("dynamic = 'force-dynamic'");
  expect(page).toContain('index: false');
  expect(page).not.toMatch(/getAccessToken|Auth0/i);
  expect(component).not.toMatch(/navigator\.mediaDevices|RTCPeerConnection|joinUrl|\/api\/v1\/calls|onSubmit|fetch\(/i);
});

test('keeps public translations aligned between Spanish and English', () => {
  const spanish = JSON.parse(readFileSync(resolve(process.cwd(), 'messages/es.json'), 'utf8')).publicVoiceExperience;
  const english = JSON.parse(readFileSync(resolve(process.cwd(), 'messages/en.json'), 'utf8')).publicVoiceExperience;

  expect(flattenKeys(spanish).sort()).toEqual(flattenKeys(english).sort());
});
