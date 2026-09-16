import { expect, test } from '@playwright/test';
import { parseVoicePreviewError, voicePreviewErrorKey } from '@/lib/voice-preview-error';
import { parseVoicePreviewMediaType } from '@/lib/voice-preview-media-type';

test('accepts only supported audio media types from the backend', () => {
  expect(parseVoicePreviewMediaType('audio/wav')).toBe('audio/wav');
  expect(parseVoicePreviewMediaType('Audio/MPEG; charset=binary')).toBe('audio/mpeg');
  expect(parseVoicePreviewMediaType('application/octet-stream')).toBeNull();
  expect(parseVoicePreviewMediaType('text/plain')).toBeNull();
  expect(parseVoicePreviewMediaType(null)).toBeNull();
});

test('preview 400 reasons map to fixed UI messages', () => {
  for (const [reason, key] of Object.entries({
    voice: 'voice', model: 'model', permission: 'permission', quota: 'quota',
    sample_rate: 'sampleRate', other: 'other',
  })) {
    const error = parseVoicePreviewError({ detail: { code: 'voice_preview_rejected', reason } });
    expect(error).toEqual({ code: 'voice_preview_rejected', reason });
    expect(voicePreviewErrorKey(error)).toBe(`voice.origin.previewErrors.${key}`);
  }
});

test('unknown provider data never becomes a client message', () => {
  const error = parseVoicePreviewError({ detail: { code: 'voice_preview_rejected', reason: 'secret_note' } });
  expect(error.reason).toBe('other');
  expect(voicePreviewErrorKey(error)).toBe('voice.origin.previewErrors.other');
  expect(parseVoicePreviewError({ detail: 'secret_note' })).toEqual({ code: 'preview_failed' });
  expect(parseVoicePreviewError({ detail: ['secret_note'] })).toEqual({ code: 'preview_failed' });
});

test('existing safe error codes stay distinct', () => {
  for (const [code, key] of Object.entries({
    provider_auth_failed: 'auth', provider_rate_limited: 'rateLimited',
    provider_unavailable: 'unavailable', provider_invalid_preview: 'invalidAudio',
    provider_preview_too_large: 'tooLarge', provider_preview_redirect_blocked: 'redirectBlocked',
    provider_resource_not_found: 'voice',
  })) {
    const error = parseVoicePreviewError({ detail: code });
    expect(error.code).toBe(code);
    expect(voicePreviewErrorKey(error)).toBe(`voice.origin.previewErrors.${key}`);
  }
});
