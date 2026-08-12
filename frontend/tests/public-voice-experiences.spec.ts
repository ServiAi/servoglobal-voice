import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { createServer, type Server } from 'node:http';
import { resolve } from 'node:path';

import type { PublicVoiceExperience as PublicVoiceExperienceData } from '../types/public-voice-experiences';

const experience: PublicVoiceExperienceData = {
  slug: 'consultation-demo',
  locale: 'es',
  version: 3,
  content: {
    title: 'Plan your consultation',
    description: 'Review the information requested before your conversation.',
    submit_label: 'Continue',
    call_label: 'Start call',
    success_message: 'Ready',
  },
  theme: {
    logo_url: null,
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
    { key: 'guests', label: 'Guests', description: null, field_type: 'integer', required: true, options: [] },
    { key: 'verified', label: 'Verified', description: 'I confirm', field_type: 'checkbox', required: true, options: [] },
    { key: 'date', label: 'Date', description: null, field_type: 'date', required: false, options: [] },
  ],
  capabilities: { submissions: true, calls: false },
};

const unsafeExperience: PublicVoiceExperienceData = {
  ...experience,
  slug: 'unsafe-urls',
  theme: { ...experience.theme, logo_url: 'javascript:alert(1)' },
  consent: { ...experience.consent, privacy_url: 'http://example.com/privacy' },
};

let apiServer: Server;
// Egress guardrail: every request the runtime makes lands here, on 127.0.0.1:43119.
// If SSR ever reached staging instead of the mock, this list would stay empty and
// the assertion in the snapshot test below would fail.
const mockRequests: string[] = [];
const submittedTokens: string[] = [];
const submittedLocales: string[] = [];
const unexpectedEgress: string[] = [];

test.beforeEach(async ({ page }) => {
  unexpectedEgress.length = 0;
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (!['127.0.0.1:3200', '127.0.0.1:43119'].includes(url.host)) {
      unexpectedEgress.push(request.url());
    }
  });
});

test.afterEach(() => {
  expect(unexpectedEgress).toEqual([]);
});

test.beforeAll(async () => {
  apiServer = createServer(async (request, response) => {
    if (request.url) mockRequests.push(request.url);
    const cors = {
      'Access-Control-Allow-Origin': 'http://127.0.0.1:3200',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    };
    if (request.method === 'OPTIONS') {
      response.writeHead(204, cors);
      response.end();
      return;
    }
    if (request.method === 'POST' && request.url?.endsWith('/submissions')) {
      const chunks: Buffer[] = [];
      for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const body = JSON.parse(Buffer.concat(chunks).toString()) as {
        answers: Record<string, unknown>;
        locale: string;
        turnstile_token: string;
      };
      submittedTokens.push(body.turnstile_token);
      submittedLocales.push(body.locale);
      const simulated = body.answers.notes;
      const errors: Record<string, [number, string, Array<{ key: string; code: string }>]> = {
        validation: [422, 'validation_error', [{ key: 'notes', code: 'too_short' }]],
        verification: [422, 'verification_failed', []],
        version: [409, 'experience_version_changed', []],
        rate: [429, 'rate_limited', []],
      };
      if (typeof simulated === 'string' && errors[simulated]) {
        const [status, code, fields] = errors[simulated];
        response.writeHead(status, { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
        response.end(JSON.stringify({ detail: { code, fields } }));
        return;
      }
      response.writeHead(200, { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({
        status: 'accepted',
        context_token: 'context-token-must-never-render',
        expires_at: '2026-08-11T12:10:00Z',
        capabilities: { submissions: true, calls: false },
      }));
      return;
    }
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

test.afterAll(() => {
  apiServer.closeAllConnections();
  apiServer.close();
});

function flattenKeys(value: unknown, prefix = ''): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => flattenKeys(child, prefix ? `${prefix}.${key}` : key));
}

test('renders all enabled field types as a responsive public form', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/en/voice/consultation-demo');

  // Egress guardrail: the render must have been served by the local mock, not staging.
  expect(mockRequests).toContain('/api/v1/public/voice-experiences/consultation-demo');

  await expect(page.getByRole('heading', { name: experience.content.title })).toBeVisible();
  await expect(page.getByText('Version 3')).toBeVisible();
  await expect(page.getByLabel('Full name')).toBeEnabled();
  await expect(page.getByLabel('Property type')).toBeEnabled();
  for (const label of ['Notes', 'Email', 'Phone', 'Guests', 'Verified', 'Date']) {
    await expect(page.getByLabel(label)).toBeEnabled();
  }
  await expect(page.getByRole('option', { name: 'House' })).toHaveAttribute('value', 'house');
  await expect(page.getByTestId('turnstile-test-mode')).toBeAttached();
  await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled();
  await expect(page.getByText('Complete the information to prepare your experience context. Calls are not enabled yet.')).toBeVisible();
  await expect(page.getByRole('link', { name: 'View privacy policy' })).toHaveAttribute('href', experience.consent.privacy_url!);
  await expect(page.getByAltText('Experience logo')).toHaveCount(0);
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

async function completeRequiredFields(page: import('@playwright/test').Page, notes?: string) {
  await page.getByLabel('Full name').fill('Ada Lovelace');
  await page.getByLabel('Guests').fill('0');
  await page.getByLabel('Property type').selectOption('house');
  if (notes) await page.getByLabel('Notes').fill(notes);
  await page.getByLabel('I accept the data policy.').check();
}

test('submits integer zero and checkbox false without exposing the context token', async ({ page, context }) => {
  await page.goto('/en/voice/consultation-demo');
  await completeRequiredFields(page);
  await expect(page.getByLabel('Verified')).not.toBeChecked();
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Information received' })).toBeVisible();
  await expect(page.getByText(experience.content.success_message)).toBeVisible();
  await expect(page.getByText('context-token-must-never-render')).toHaveCount(0);
  expect(await page.evaluate(() => ({ local: { ...localStorage }, session: { ...sessionStorage }, cookie: document.cookie })))
    .toEqual({ local: {}, session: {}, cookie: '' });
  expect((await context.cookies()).some((cookie) => cookie.value.includes('context-token'))).toBe(false);
});

test('submits the URL locale instead of the snapshot default locale', async ({ page }) => {
  const start = submittedLocales.length;
  for (const locale of ['en', 'es']) {
    await page.goto(`/${locale}/voice/consultation-demo`);
    await page.locator('#public-field-full_name').fill('Ada Lovelace');
    await page.locator('#public-field-guests').fill('0');
    await page.locator('#public-field-property_type').selectOption('house');
    await page.locator('#public-consent').check();
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect.poll(() => submittedLocales.length).toBe(start + (locale === 'en' ? 1 : 2));
  }
  expect(submittedLocales.slice(start)).toEqual(['en', 'es']);
});

test('renews the single-use token after validation failure before retrying', async ({ page }) => {
  const start = submittedTokens.length;
  await page.goto('/en/voice/consultation-demo');
  await completeRequiredFields(page, 'validation');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByText('The value is too short.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled();
  await page.getByLabel('Notes').fill('corrected');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Information received' })).toBeVisible();
  expect(submittedTokens.slice(start)).toHaveLength(2);
  expect(submittedTokens[start]).not.toBe(submittedTokens[start + 1]);
});

test('clears a verification-failed token and disables submission until renewal', async ({ page }) => {
  const start = submittedTokens.length;
  await page.goto('/en/voice/consultation-demo');
  await completeRequiredFields(page, 'verification');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByText('Verification expired or failed. Complete the new verification.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue' })).toBeEnabled();
  await page.getByLabel('Notes').fill('renewed');
  await page.getByRole('button', { name: 'Continue' }).click();
  expect(submittedTokens[start]).not.toBe(submittedTokens[start + 1]);
});

for (const [value, message] of [
  ['version', 'The form changed. Reload the page before continuing.'],
  ['rate', 'Too many attempts. Wait a minute and try again.'],
] as const) {
  test(`renders translated ${value} errors without backend text`, async ({ page }) => {
    await page.goto('/en/voice/consultation-demo');
    await completeRequiredFields(page, value);
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(page.getByText(message)).toBeVisible();
  });
}

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
  expect(component).not.toMatch(/navigator\.mediaDevices|RTCPeerConnection|joinUrl|\/api\/v1\/calls|localStorage|sessionStorage|document\.cookie/i);
  expect(component).toContain("NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE === '1'");
  expect(component).not.toMatch(/NODE_ENV|hostname|localhost/);
  expect(component).toContain('disabled={!turnstileToken || isSubmitting}');
});

test('keeps public translations aligned between Spanish and English', () => {
  const spanish = JSON.parse(readFileSync(resolve(process.cwd(), 'messages/es.json'), 'utf8')).publicVoiceExperience;
  const english = JSON.parse(readFileSync(resolve(process.cwd(), 'messages/en.json'), 'utf8')).publicVoiceExperience;

  expect(flattenKeys(spanish).sort()).toEqual(flattenKeys(english).sort());
});
