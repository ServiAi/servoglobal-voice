export type PublicCallErrorCode =
  | 'experience_unavailable'
  | 'experience_version_changed'
  | 'call_already_started'
  | 'call_state_conflict'
  | 'context_session_unavailable'
  | 'context_session_expired'
  | 'validation_error'
  | 'rate_limited'
  | 'call_unavailable'
  | 'call_provider_unavailable'
  | 'phone_unavailable'
  | 'destination_not_allowed'
  | 'call_capacity_reached'
  | 'internal_error';

export type PublicCallResult =
  | { ok: true; data: { status: 'ready'; join_url: string } }
  | { ok: false; error: PublicCallErrorCode };

export async function launchPublicVoiceCall(slug: string, contextToken: string): Promise<PublicCallResult> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  try {
    const response = await fetch(`${baseUrl}/api/v1/public/voice-experiences/${encodeURIComponent(slug)}/calls`, {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ context_token: contextToken }),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return { ok: false, error: body?.detail?.code || 'internal_error' };
    return { ok: true, data: body };
  } catch {
    return { ok: false, error: 'internal_error' };
  }
}

export async function requestPublicVoiceCallback(
  slug: string,
  contextToken: string,
): Promise<{ ok: true } | { ok: false; error: PublicCallErrorCode }> {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
  try {
    const response = await fetch(
      `${baseUrl}/api/v1/public/voice-experiences/${encodeURIComponent(slug)}/callback-requests`,
      {
        method: 'POST',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context_token: contextToken }),
      },
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) return { ok: false, error: body?.detail?.code || 'internal_error' };
    return { ok: true };
  } catch {
    return { ok: false, error: 'internal_error' };
  }
}
