import type { MeProfile } from '@/lib/api/me';
import type { CustomToolGateState } from '@/types/tools-custom';

const READ_ROLES = new Set(['platform_admin', 'tenant_admin', 'tenant_analyst', 'tenant_viewer']);
const WRITE_ROLES = new Set(['platform_admin', 'tenant_admin']);

export function canReadCustomTools(profile: Pick<MeProfile, 'role'>) {
  return READ_ROLES.has(profile.role);
}

export function canEditCustomTools(profile: Pick<MeProfile, 'role'>) {
  return WRITE_ROLES.has(profile.role);
}

export function resolveCustomToolsGateState({
  canRead,
  listStatus,
}: {
  canRead: boolean;
  listStatus: number | null;
}): CustomToolGateState {
  if (!canRead) return 'access_denied';
  if (listStatus === 403) return 'feature_disabled';
  if (listStatus !== null) return 'error';
  return 'ok';
}
