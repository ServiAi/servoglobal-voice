import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: /(livekit-adapter|crm-voice-call-contract|voice-preview-error|agent-builder-field-help)\.spec\.ts$/,
  workers: 1,
});
