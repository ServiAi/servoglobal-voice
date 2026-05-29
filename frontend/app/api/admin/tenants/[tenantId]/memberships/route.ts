import { NextResponse } from 'next/server';

import {
  addTenantMembership,
  type MembershipCreatePayload,
} from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

type RouteContext = {
  params: Promise<{ tenantId: string }>;
};

export const dynamic = 'force-dynamic';

export async function POST(request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  let payload: MembershipCreatePayload;
  try {
    payload = (await request.json()) as MembershipCreatePayload;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const { tenantId } = await params;
  return adminJsonResponse(
    await addTenantMembership(auth.accessToken, tenantId, payload),
    201
  );
}
