import { defineConfig } from '@playwright/test';

// Dedicated Playwright config for the PUBLIC voice runtime E2E suite.
// - Runs only public-voice-experiences.spec.ts.
// - No storageState / no Auth0: the public runtime is unauthenticated by design.
// - Boots Next.js on its own port and points SSR at the in-test HTTP mock
//   (127.0.0.1:43119) via NEXT_PUBLIC_API_URL, so there is zero egress to staging.
const port = 3200;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: /public-voice-experiences\.spec\.ts/,
  outputDir: 'test-results-public',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [['list']],
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    browserName: 'chromium',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `npm run dev -- -p ${port}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // The public SSR client reads this at request time; the mock at 43119 is the
      // ONLY backend the runtime is allowed to reach during the public suite.
      NEXT_PUBLIC_API_URL: 'http://127.0.0.1:43119',
      NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE: '1',
    },
  },
  projects: [{ name: 'public' }],
});
