import 'server-only';

import { providerVoicePreviewUrl } from './voice-provider-admin';
import type { AgentVoiceConfig } from '@/types/agents';

export type VoicePreviewResult =
  | { ok: true; audioBase64: string }
  | { ok: false; status: number; detail: string };

// Server-only: fetches an audio/wav preview and hands the caller back
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
    return { ok: false, status: 502, detail: 'Voice provider API is temporarily unavailable' };
  }
  if (!response.ok) {
    let detail = 'Voice preview failed';
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // ignore: not every error response is JSON
    }
    return { ok: false, status: response.status, detail };
  }
  const buffer = Buffer.from(await response.arrayBuffer());
  return { ok: true, audioBase64: buffer.toString('base64') };
}

export function previewProviderVoiceAudio(
  accessToken: string,
  provider: string,
  voiceId: string
): Promise<VoicePreviewResult> {
  const url = providerVoicePreviewUrl(provider, voiceId);
  if (!url) return Promise.resolve({ ok: false, status: 500, detail: 'Backend API URL is not configured' });
  return fetchAudioPreview(url, accessToken);
}

export function previewExternalVoiceAudio(
  accessToken: string,
  provider: string,
  voice: AgentVoiceConfig
): Promise<VoicePreviewResult> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) return Promise.resolve({ ok: false, status: 500, detail: 'Backend API URL is not configured' });
  const url = `${apiUrl.replace(/\/$/, '')}/api/v1/integrations/voice/providers/${provider}/external-voice/preview`;
  return fetchAudioPreview(url, accessToken, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(voice),
  });
}
