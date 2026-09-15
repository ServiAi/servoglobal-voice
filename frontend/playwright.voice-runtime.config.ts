import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: /(livekit-adapter|crm-voice-call-contract)\.spec\.ts$/,
  workers: 1,
});
