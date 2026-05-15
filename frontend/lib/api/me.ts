export type MeProfile = {
  user_id: string;
  email: string;
  name: string | null;
  tenant_id: string;
  tenant_name: string;
  role: string;
  is_internal: boolean;
};

export type MeResult =
  | { ok: true; profile: MeProfile }
  | { ok: false; status: number; detail: string };

export async function fetchMeProfile(accessToken: string): Promise<MeResult> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return { ok: false, status: 500, detail: 'Backend API URL is not configured' };
  }

  let response: Response;
  try {
    response = await fetch(`${apiUrl.replace(/\/$/, '')}/api/v1/me`, {
      headers: {
        Authorization: `Bearer ${accessToken}`
      },
      cache: 'no-store'
    });
  } catch (error) {
    console.error('Profile API request failed', error);
    return {
      ok: false,
      status: 502,
      detail: 'Profile API is temporarily unavailable',
    };
  }

  if (!response.ok) {
    let detail = 'Unable to resolve the authenticated profile';
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Keep a controlled generic message.
    }
    return { ok: false, status: response.status, detail };
  }

  return { ok: true, profile: (await response.json()) as MeProfile };
}
