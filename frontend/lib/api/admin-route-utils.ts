import 'server-only';

import { NextResponse } from 'next/server';

import { getAccessToken } from '@/lib/auth/server';
import { type FetchResult } from '@/lib/api/tenants';

export async function requireAdminAccessToken(): Promise<
  | { ok: true; accessToken: string }
  | { ok: false; response: NextResponse<{ detail: string }> }
> {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return {
      ok: false,
      response: NextResponse.json(
        { detail: 'Authentication token is required' },
        { status: 401 }
      ),
    };
  }

  return { ok: true, accessToken };
}

export function adminJsonResponse<T>(
  result: FetchResult<T>,
  successStatus = 200
): NextResponse<T | { detail: string }> {
  if (!result.ok) {
    return NextResponse.json(
      { detail: result.detail },
      { status: result.status }
    );
  }

  return NextResponse.json(result.data, { status: successStatus });
}
