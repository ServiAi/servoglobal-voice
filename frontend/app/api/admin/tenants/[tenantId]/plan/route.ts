import { NextResponse } from 'next/server';

import {
  updateTenantPlan,
  type TenantPlanPayload,
} from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

type RouteContext = {
  params: Promise<{ tenantId: string }>;
};

export const dynamic = 'force-dynamic';

export async function PATCH(request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  let payload: TenantPlanPayload;
  try {
    payload = (await request.json()) as TenantPlanPayload;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const { tenantId } = await params;
  return adminJsonResponse(
    await updateTenantPlan(auth.accessToken, tenantId, payload)
  );
}
