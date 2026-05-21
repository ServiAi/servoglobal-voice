import { NextResponse } from 'next/server';

import {
  createTenant,
  fetchTenantsList,
  type TenantCreatePayload,
} from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

export const dynamic = 'force-dynamic';

export async function GET() {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  return adminJsonResponse(await fetchTenantsList(auth.accessToken));
}

export async function POST(request: Request) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  let payload: TenantCreatePayload;
  try {
    payload = (await request.json()) as TenantCreatePayload;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  return adminJsonResponse(await createTenant(auth.accessToken, payload), 201);
}
