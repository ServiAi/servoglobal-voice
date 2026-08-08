import 'server-only';

import type { PublicVoiceExperience } from '@/types/public-voice-experiences';

export type PublicVoiceFetchResult =
  | { ok: true; data: PublicVoiceExperience }
  | { ok: false; status: number; detail: string };

export async function fetchPublicVoiceExperience(slug: string): Promise<PublicVoiceFetchResult> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl) {
    return { ok: false, status: 503, detail: 'Public API unavailable' };
  }

  try {
    const response = await fetch(
      `${apiUrl}/api/v1/public/voice-experiences/${encodeURIComponent(slug)}`,
      { cache: 'no-store', headers: { Accept: 'application/json' } },
    );

    if (!response.ok) {
      return { ok: false, status: response.status, detail: 'Voice experience unavailable' };
    }

    return { ok: true, data: (await response.json()) as PublicVoiceExperience };
  } catch {
    return { ok: false, status: 503, detail: 'Public API unavailable' };
  }
}
