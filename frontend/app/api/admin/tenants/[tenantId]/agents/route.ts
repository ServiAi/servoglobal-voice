import { NextResponse } from 'next/server';

import { addTenantAgent, type AgentCreatePayload } from '@/lib/api/tenants';
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

  let payload: AgentCreatePayload;
  try {
    payload = (await request.json()) as AgentCreatePayload;
  } catch {
    return NextResponse.json({ detail: 'Invalid JSON body' }, { status: 400 });
  }

  const { tenantId } = await params;
  return adminJsonResponse(
    await addTenantAgent(auth.accessToken, tenantId, payload),
    201
  );
}
