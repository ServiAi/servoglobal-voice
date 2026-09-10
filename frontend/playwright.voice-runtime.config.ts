import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: /livekit-adapter\.spec\.ts$/,
  workers: 1,
});
