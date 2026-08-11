import { defineConfig } from '@playwright/test';

const port = 3201;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: /public-voice-turnstile-unavailable\.spec\.ts/,
  outputDir: 'test-results-public-no-turnstile',
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: { baseURL, browserName: 'chromium' },
  webServer: {
    command: `npm run dev -- -p ${port}`,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_URL: 'http://127.0.0.1:43120',
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: '',
      NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE: '0',
    },
  },
  projects: [{ name: 'public-no-turnstile' }],
});
