import { rmSync } from 'node:fs';
import { defineConfig } from '@playwright/test';

// next dev is started directly (see webServer.command), so replicate the
// clean:next step the old `npm run dev` did on every boot: a stale .next
// cache makes Next reparse tailwind.config.ts as ESM (require -> crash).
// Only the main runner imports this config before the server boots; workers
// re-import it mid-run, so skip them or they would wipe the live .next.
if (process.env.TEST_WORKER_INDEX === undefined && process.env.PLAYWRIGHT_EXTERNAL_PUBLIC_SERVER !== '1') {
  rmSync('.next', { recursive: true, force: true });
}

// Dedicated Playwright config for the PUBLIC voice runtime E2E suite.
// - Runs public-voice-experiences.spec.ts and public-voice-embed.spec.ts.
// - No storageState / no Auth0: the public runtime is unauthenticated by design.
// - Boots Next.js on its own port and points SSR at the in-test HTTP mock
//   (127.0.0.1:43119) via NEXT_PUBLIC_API_URL, so there is zero egress to staging.
const port = 3200;
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: './tests',
  testMatch: /public-voice-(experiences|embed)\.spec\.ts/,
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
  webServer: process.env.PLAYWRIGHT_EXTERNAL_PUBLIC_SERVER === '1' ? undefined : {
    command: `node ./node_modules/next/dist/bin/next dev -p ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      // The public SSR client reads this at request time; the mock at 43119 is the
      // ONLY backend the runtime is allowed to reach during the public suite.
      NEXT_PUBLIC_API_URL: 'http://127.0.0.1:43119',
      NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE: '1',
      NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE: '1',
    },
  },
  projects: [{ name: 'public' }],
});
