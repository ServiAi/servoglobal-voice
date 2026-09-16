export type VoicePreviewErrorReason = 'voice' | 'model' | 'permission' | 'quota' | 'sample_rate' | 'other';

const reasons = new Set<VoicePreviewErrorReason>(['voice', 'model', 'permission', 'quota', 'sample_rate', 'other']);
const codes = new Set([
  'voice_preview_rejected', 'provider_auth_failed', 'provider_rate_limited', 'provider_unavailable',
  'provider_invalid_preview', 'provider_preview_too_large', 'provider_preview_redirect_blocked',
  'provider_resource_not_found', 'provider_rejected', 'external_voice_preview_failed',
]);

export function parseVoicePreviewError(payload: unknown): { code: string; reason?: VoicePreviewErrorReason } {
  const detail = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? (payload as Record<string, unknown>).detail : undefined;
  const error = detail && typeof detail === 'object' && !Array.isArray(detail)
    ? detail as Record<string, unknown> : null;
  const rawCode = typeof detail === 'string' ? detail : error?.code;
  const code = typeof rawCode === 'string' && codes.has(rawCode) ? rawCode : 'preview_failed';
  if (code !== 'voice_preview_rejected') return { code };
  const rawReason = error?.reason;
  return { code, reason: typeof rawReason === 'string' && reasons.has(rawReason as VoicePreviewErrorReason)
    ? rawReason as VoicePreviewErrorReason : 'other' };
}

const reasonKeys = {
  voice: 'voice.origin.previewErrors.voice',
  model: 'voice.origin.previewErrors.model',
  permission: 'voice.origin.previewErrors.permission',
  quota: 'voice.origin.previewErrors.quota',
  sample_rate: 'voice.origin.previewErrors.sampleRate',
  other: 'voice.origin.previewErrors.other',
} as const;

const codeKeys: Record<string, string> = {
  provider_auth_failed: 'voice.origin.previewErrors.auth',
  provider_rate_limited: 'voice.origin.previewErrors.rateLimited',
  provider_unavailable: 'voice.origin.previewErrors.unavailable',
  provider_invalid_preview: 'voice.origin.previewErrors.invalidAudio',
  provider_preview_too_large: 'voice.origin.previewErrors.tooLarge',
  provider_preview_redirect_blocked: 'voice.origin.previewErrors.redirectBlocked',
  provider_resource_not_found: 'voice.origin.previewErrors.voice',
};

export function voicePreviewErrorKey(error: { code: string; reason?: VoicePreviewErrorReason }): string {
  return error.code === 'voice_preview_rejected'
    ? reasonKeys[error.reason ?? 'other']
    : codeKeys[error.code] ?? 'voice.origin.previewFailed';
}
