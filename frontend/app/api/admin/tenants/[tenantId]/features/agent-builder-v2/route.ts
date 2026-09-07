import { NextResponse } from 'next/server';

import { setAgentBuilderFeature } from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

type RouteContext = {
  params: Promise<{ tenantId: string }>;
};

export const dynamic = 'force-dynamic';

export async function PUT(request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  let payload: { enabled: boolean };
  try {
    payload = (await request.json()) as { enabled: boolean };
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const { tenantId } = await params;
  return adminJsonResponse(
    await setAgentBuilderFeature(auth.accessToken, tenantId, payload.enabled)
  );
}
