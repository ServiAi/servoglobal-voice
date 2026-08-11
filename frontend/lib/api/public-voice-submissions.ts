import type {
  PublicSubmissionErrorCode,
  PublicSubmissionFailure,
  PublicSubmissionResponse,
} from '@/types/public-voice-experiences';

const ERROR_CODES = new Set<PublicSubmissionErrorCode>([
  'experience_version_changed',
  'validation_error',
  'verification_failed',
  'rate_limited',
  'internal_error',
]);

export async function submitPublicVoiceExperience(
  slug: string,
  payload: {
    version: number;
    locale: string;
    answers: Record<string, string | number | boolean | null>;
    consent: boolean;
    turnstile_token: string;
    hp: string;
  },
): Promise<{ ok: true; data: PublicSubmissionResponse } | { ok: false; error: PublicSubmissionFailure }> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '');
  if (!apiUrl) return { ok: false, error: { code: 'verification_failed', fields: [] } };

  try {
    const response = await fetch(
      `${apiUrl}/api/v1/public/voice-experiences/${encodeURIComponent(slug)}/submissions`,
      {
        method: 'POST',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        cache: 'no-store',
      },
    );
    const body = (await response.json().catch(() => null)) as {
      detail?: { code?: unknown; fields?: unknown };
    } | PublicSubmissionResponse | null;
    if (response.ok) return { ok: true, data: body as PublicSubmissionResponse };

    const code = body && 'detail' in body ? body.detail?.code : null;
    const fields = body && 'detail' in body && Array.isArray(body.detail?.fields) ? body.detail.fields : [];
    return {
      ok: false,
      error: {
        code: typeof code === 'string' && ERROR_CODES.has(code as PublicSubmissionErrorCode)
          ? (code as PublicSubmissionErrorCode)
          : 'validation_error',
        fields: fields as PublicSubmissionFailure['fields'],
      },
    };
  } catch {
    return { ok: false, error: { code: 'verification_failed', fields: [] } };
  }
}
