import { rmSync } from 'node:fs';
import { defineConfig } from '@playwright/test';

// next dev is started directly (see webServer.command), so replicate the
// clean:next step the old `npm run dev` did on every boot: a stale .next
// cache makes Next reparse tailwind.config.ts as ESM (require -> crash).
// Only the main runner imports this config before the server boots; workers
// re-import it mid-run, so skip them or they would wipe the live .next.
if (process.env.TEST_WORKER_INDEX === undefined) {
  rmSync('.next', { recursive: true, force: true });
}

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
    command: `node ./node_modules/next/dist/bin/next dev -p ${port}`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_URL: 'http://127.0.0.1:43120',
      NEXT_PUBLIC_TURNSTILE_SITE_KEY: '',
      NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE: '0',
    },
  },
  projects: [{ name: 'public-no-turnstile' }],
});
