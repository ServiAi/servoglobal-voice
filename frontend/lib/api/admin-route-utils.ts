import 'server-only';

import { NextResponse } from 'next/server';

import { type FetchResult } from '@/lib/api/tenants';
import { resolveInternalAdminAccess } from '@/lib/auth/server';

export async function requireAdminAccessToken(): Promise<
  | { ok: true; accessToken: string }
  | { ok: false; response: NextResponse<{ detail: string }> }
> {
  const result = await resolveInternalAdminAccess();

  if (!result.ok) {
    return {
      ok: false,
      response: NextResponse.json(
        { detail: result.detail },
        { status: result.status }
      ),
    };
  }

  return { ok: true, accessToken: result.context.accessToken };
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
