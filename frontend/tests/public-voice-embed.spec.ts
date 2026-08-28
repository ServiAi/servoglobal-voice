import { expect, test } from '@playwright/test';
import { createServer, type Server } from 'node:http';

import type { PublicVoiceExperience as PublicVoiceExperienceData } from '../types/public-voice-experiences';

const baseExperience: PublicVoiceExperienceData = {
  slug: 'embed-demo',
  locale: 'es',
  version: 1,
  content: {
    title: 'Habla con nuestro asesor',
    description: 'Completa tus datos para comenzar.',
    submit_label: 'Continuar',
    call_label: 'Iniciar llamada',
    success_message: 'Tus datos fueron registrados.',
  },
  theme: {
    logo_url: null,
    primary_color: '#0f766e',
    background_color: null,
    color_scheme: 'light',
    layout: 'centered',
  },
  consent: { required: false, label: null, privacy_url: null },
  fields: [
    { key: 'full_name', label: 'Nombre completo', description: null, field_type: 'text', required: true, options: [] },
  ],
  call_settings: {
    auto_start: false,
    show_microphone_help: true,
    language: 'es',
    mode: 'webrtc',
    phone_field_key: null,
    default_country: 'CO',
    allowed_countries: ['CO'],
  },
  capabilities: { submissions: true, calls: true },
};

const darkExperience: PublicVoiceExperienceData = {
  ...baseExperience,
  slug: 'embed-dark-demo',
  theme: { ...baseExperience.theme, color_scheme: 'dark' },
};

const customBackgroundExperience: PublicVoiceExperienceData = {
  ...baseExperience,
  slug: 'embed-custom-bg-demo',
  theme: { ...baseExperience.theme, color_scheme: 'light', background_color: '#FFE4E6' },
};

let apiServer: Server;
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
    if (request.url === '/embed-host.html') {
      // A real http(s) parent page, matching how a tenant's own site embeds the
      // widget. CSP frame-ancestors '*' deliberately excludes non-network-scheme
      // parents (about:blank, data:), so this must be served over real HTTP.
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <!doctype html>
        <html><body style="margin:0">
          <iframe id="voice-frame" src="http://127.0.0.1:3200/es/voice/embed-demo/embed" style="width:400px;height:400px;border:0"></iframe>
          <script>
            window.__lastResize = null;
            window.addEventListener('message', (event) => {
              if (event.data && event.data.type === 'voice-embed:resize') {
                window.__lastResize = event.data;
              }
            });
          </script>
        </body></html>
      `);
      return;
    }
    if (request.url === '/inline-sdk-host.html') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <!doctype html>
        <html><body style="margin:0">
          <div data-voice-embed="inline" data-voice-embed-src="http://127.0.0.1:3200/es/voice/embed-demo/embed"></div>
          <script src="http://127.0.0.1:3200/voice-embed.v1.js" async></script>
        </body></html>
      `);
      return;
    }
    if (request.url === '/floating-sdk-host.html') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <!doctype html>
        <html><body style="margin:0">
          <script src="http://127.0.0.1:3200/voice-embed.v1.js" async
            data-voice-embed="floating"
            data-voice-embed-src="http://127.0.0.1:3200/es/voice/embed-demo/embed"
            data-voice-embed-text="Habla con nosotros"
            data-voice-embed-position="bottom-right"></script>
        </body></html>
      `);
      return;
    }
    if (request.url === '/modal-sdk-host.html') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end(`
        <!doctype html>
        <html><body style="margin:0">
          <button id="reservar-demo" type="button">Reservar demo</button>
          <script src="http://127.0.0.1:3200/voice-embed.v1.js" async
            data-voice-embed="modal"
            data-voice-embed-src="http://127.0.0.1:3200/es/voice/embed-demo/embed"
            data-voice-embed-trigger="#reservar-demo"></script>
        </body></html>
      `);
      return;
    }
    if (request.method === 'POST' && request.url?.endsWith('/submissions')) {
      const chunks: Buffer[] = [];
      for await (const chunk of request) chunks.push(Buffer.from(chunk));
      JSON.parse(Buffer.concat(chunks).toString());
      response.writeHead(200, { ...cors, 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({
        status: 'accepted',
        context_token: 'context-token-must-never-render',
        expires_at: '2026-08-11T12:10:00Z',
        capabilities: { submissions: true, calls: false },
      }));
      return;
    }
    const data = request.url?.endsWith('/embed-dark-demo')
      ? darkExperience
      : request.url?.endsWith('/embed-custom-bg-demo')
        ? customBackgroundExperience
        : baseExperience;
    response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    response.end(JSON.stringify(data));
  });
  await new Promise<void>((resolveListen) => apiServer.listen(43119, '127.0.0.1', resolveListen));
});

test.afterAll(() => {
  apiServer.closeAllConnections();
  apiServer.close();
});

test('embed route strips full-page chrome and has no footer', async ({ page }) => {
  await page.goto('/es/voice/embed-demo/embed');
  await expect(page.getByTestId('public-voice-runtime')).not.toHaveClass(/min-h-screen/);
  await expect(page.locator('footer')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: baseExperience.content.title })).toBeVisible();
});

test('light theme renders the default light tokens', async ({ page }) => {
  await page.goto('/es/voice/embed-demo/embed');
  const bg = await page.locator('[data-testid="public-voice-runtime"]').evaluate(
    (el) => getComputedStyle(el.parentElement!).backgroundColor
  );
  expect(bg).toBe('rgb(244, 247, 246)');
});

test('dark color_scheme renders dark tokens', async ({ page }) => {
  await page.goto('/es/voice/embed-dark-demo/embed');
  const bg = await page.locator('[data-testid="public-voice-runtime"]').evaluate(
    (el) => getComputedStyle(el.parentElement!).backgroundColor
  );
  expect(bg).toBe('rgb(15, 23, 42)');
});

test('custom background_color overrides the scheme default', async ({ page }) => {
  await page.goto('/es/voice/embed-custom-bg-demo/embed');
  const bg = await page.locator('[data-testid="public-voice-runtime"]').evaluate(
    (el) => getComputedStyle(el.parentElement!).backgroundColor
  );
  expect(bg).toBe('rgb(255, 228, 230)');
});

test('small viewport has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto('/es/voice/embed-demo/embed');
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.scrollWidth,
    viewport: window.innerWidth,
  }));
  expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
});

test('submission still works end-to-end inside the embed route', async ({ page }) => {
  await page.goto('/es/voice/embed-demo/embed');
  await page.getByLabel('Nombre completo').fill('Ada Lovelace');
  await page.getByRole('button', { name: 'Continuar' }).click();
  await expect(page.getByText(baseExperience.content.success_message)).toBeVisible();
});

test('resizing the embedded content posts voice-embed:resize to the parent frame', async ({ page }) => {
  // Navigates to a real http origin (not about:blank) so the embed route's
  // `frame-ancestors *` CSP actually permits framing it, matching how a real
  // tenant website (always http/https) would embed the widget.
  await page.goto('http://127.0.0.1:43119/embed-host.html');
  await page.waitForFunction(() => (window as unknown as { __lastResize: unknown }).__lastResize !== null);
  const message = await page.evaluate(() => (window as unknown as { __lastResize: { type: string; slug: string; height: number } }).__lastResize);
  expect(message.type).toBe('voice-embed:resize');
  expect(message.slug).toBe('embed-demo');
  expect(typeof message.height).toBe('number');
  expect(message.height).toBeGreaterThan(0);
});

test('SDK inline mode mounts the iframe immediately', async ({ page }) => {
  await page.goto('http://127.0.0.1:43119/inline-sdk-host.html');
  const iframe = page.locator('iframe');
  await expect(iframe).toHaveCount(1);
  await expect(iframe).toHaveAttribute('allow', 'microphone; autoplay');
});

test('SDK floating mode lazily mounts the iframe only on first click', async ({ page }) => {
  await page.goto('http://127.0.0.1:43119/floating-sdk-host.html');
  const button = page.getByRole('button', { name: 'Habla con nosotros' });
  await expect(button).toBeVisible();
  await expect(page.locator('iframe')).toHaveCount(0);
  await button.click();
  await expect(page.locator('iframe')).toHaveCount(1);
});

test('SDK modal mode lazily mounts the iframe only on first click', async ({ page }) => {
  await page.goto('http://127.0.0.1:43119/modal-sdk-host.html');
  await expect(page.locator('iframe')).toHaveCount(0);
  await page.locator('#reservar-demo').click();
  await expect(page.locator('iframe')).toHaveCount(1);
});

test('the SDK auto-resizes an inline iframe from the real embed page height', async ({ page }) => {
  // The mounted iframe loads the real embed route, which already posts its own
  // resize message via ResizeObserver (verified above). This confirms the SDK's
  // own message listener (correlating by contentWindow === event.source) picks
  // that up end-to-end, without needing to fake postMessage delivery.
  await page.goto('http://127.0.0.1:43119/inline-sdk-host.html');
  const iframe = page.locator('iframe');
  await expect(iframe).toHaveCount(1);
  await expect
    .poll(async () => iframe.evaluate((el) => (el as HTMLIFrameElement).style.height))
    .toMatch(/^\d+px$/);
});
