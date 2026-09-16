import 'server-only';

import { providerVoicePreviewUrl } from './voice-provider-admin';
import { parseVoicePreviewError, type VoicePreviewErrorReason } from '../voice-preview-error';
import { parseVoicePreviewMediaType, type VoicePreviewMediaType } from '../voice-preview-media-type';
import type { AgentVoiceConfig } from '@/types/agents';

export type VoicePreviewResult =
  | { ok: true; audioBase64: string; mediaType: VoicePreviewMediaType }
  | { ok: false; status: number; code: string; reason?: VoicePreviewErrorReason };

// Server-only: fetches an audio preview and hands the caller back
// base64, never a raw bearer-token-bearing URL for the browser to hit
// directly. The Agent Builder client calls these through Server Actions
// (see voice-ai/agents/actions.ts), so the access token never reaches the
// client -- matching this app's server-action-only mutation pattern. Kept
// out of voice-provider-admin.ts (which VoiceProviderAdminWorkspace, a
// client component, also imports) so this module's Node-only Buffer usage
// never has to be considered for the client bundle.
async function fetchAudioPreview(url: string, accessToken: string, init?: RequestInit): Promise<VoicePreviewResult> {
  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      headers: { Authorization: `Bearer ${accessToken}`, ...(init?.headers ?? {}) },
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 502, code: 'provider_unavailable' };
  }
  if (!response.ok) {
    try {
      return { ok: false, status: response.status, ...parseVoicePreviewError(await response.json()) };
    } catch {
      return { ok: false, status: response.status, code: 'preview_failed' };
    }
  }
  const mediaType = parseVoicePreviewMediaType(response.headers.get('content-type'));
  if (!mediaType) return { ok: false, status: 502, code: 'provider_invalid_preview' };
  const buffer = Buffer.from(await response.arrayBuffer());
  return { ok: true, audioBase64: buffer.toString('base64'), mediaType };
}

export function previewProviderVoiceAudio(
  accessToken: string,
  provider: string,
  voiceId: string
): Promise<VoicePreviewResult> {
  const url = providerVoicePreviewUrl(provider, voiceId);
  if (!url) return Promise.resolve({ ok: false, status: 500, code: 'preview_failed' });
  return fetchAudioPreview(url, accessToken);
}

export function previewExternalVoiceAudio(
  accessToken: string,
  provider: string,
  voice: AgentVoiceConfig
): Promise<VoicePreviewResult> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) return Promise.resolve({ ok: false, status: 500, code: 'preview_failed' });
  const url = `${apiUrl.replace(/\/$/, '')}/api/v1/integrations/voice/providers/${provider}/external-voice/preview`;
  return fetchAudioPreview(url, accessToken, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(voice),
  });
}
