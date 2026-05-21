import { NextResponse } from 'next/server';

import {
  fetchTenantDetail,
  updateTenant,
  type TenantUpdatePayload,
} from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

type RouteContext = {
  params: Promise<{ tenantId: string }>;
};

export const dynamic = 'force-dynamic';

export async function GET(_request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  const { tenantId } = await params;
  return adminJsonResponse(await fetchTenantDetail(auth.accessToken, tenantId));
}

export async function PATCH(request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  let payload: TenantUpdatePayload;
  try {
    payload = (await request.json()) as TenantUpdatePayload;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const { tenantId } = await params;
  return adminJsonResponse(
    await updateTenant(auth.accessToken, tenantId, payload)
  );
}
