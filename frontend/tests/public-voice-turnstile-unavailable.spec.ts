import { expect, test } from '@playwright/test';
import { createServer, type Server } from 'node:http';

let apiServer: Server;
const methods: string[] = [];

test.beforeAll(async () => {
  apiServer = createServer((request, response) => {
    methods.push(request.method || '');
    response.writeHead(200, {
      'Access-Control-Allow-Origin': 'http://127.0.0.1:3201',
      'Content-Type': 'application/json',
      'Cache-Control': 'no-store',
    });
    response.end(JSON.stringify({
      slug: 'no-turnstile',
      locale: 'es',
      version: 1,
      content: {
        title: 'Secure context', description: null, submit_label: 'Continue',
        call_label: 'Call', success_message: 'Ready',
      },
      theme: { logo_url: null, primary_color: '#0f766e', layout: 'card' },
      consent: { required: false, label: null, privacy_url: null },
      fields: [],
      capabilities: { submissions: true, calls: false },
    }));
  });
  await new Promise<void>((resolve) => apiServer.listen(43120, '127.0.0.1', resolve));
});

test.afterAll(() => {
  apiServer.closeAllConnections();
  apiServer.close();
});

test('fails closed when the Turnstile site key and test mode are absent', async ({ page }) => {
  const externalRequests: string[] = [];
  page.on('request', (request) => {
    const host = new URL(request.url()).host;
    if (!['127.0.0.1:3201', '127.0.0.1:43120'].includes(host)) externalRequests.push(request.url());
  });

  await page.goto('/en/voice/no-turnstile');

  await expect(page.getByText('Verification is unavailable. Please try again later.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Continue' })).toBeDisabled();
  await expect(page.getByTestId('turnstile-test-mode')).toHaveCount(0);
  expect(methods).toEqual(['GET']);
  expect(externalRequests).toEqual([]);
});
