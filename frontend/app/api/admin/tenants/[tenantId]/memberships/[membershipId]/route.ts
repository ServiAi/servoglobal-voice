import { deleteTenantMembership } from '@/lib/api/tenants';
import {
  adminJsonResponse,
  requireAdminAccessToken,
} from '@/lib/api/admin-route-utils';

type RouteContext = {
  params: Promise<{ tenantId: string; membershipId: string }>;
};

export const dynamic = 'force-dynamic';

export async function DELETE(_request: Request, { params }: RouteContext) {
  const auth = await requireAdminAccessToken();
  if (!auth.ok) {
    return auth.response;
  }

  const { tenantId, membershipId } = await params;
  return adminJsonResponse(
    await deleteTenantMembership(auth.accessToken, tenantId, membershipId)
  );
}
