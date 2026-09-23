import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: /(livekit-adapter|crm-voice-call-contract|voice-preview-error|agent-builder-field-help|agent-voice-qa)\.spec\.ts$/,
  workers: 1,
});
