import type { MeProfile } from '@/lib/api/me';
import type { AgentGateState } from '@/types/agents';

const READ_ROLES = new Set(['platform_admin', 'tenant_admin', 'tenant_analyst', 'tenant_viewer']);
const WRITE_ROLES = new Set(['platform_admin', 'tenant_admin']);

export function canReadAgents(profile: Pick<MeProfile, 'role'>) {
  return READ_ROLES.has(profile.role);
}

export function canEditAgents(profile: Pick<MeProfile, 'role'>) {
  return WRITE_ROLES.has(profile.role);
}

export function resolveAgentGateState({
  canRead,
  agentsStatus,
}: {
  canRead: boolean;
  agentsStatus: number | null;
}): AgentGateState {
  if (!canRead) return 'access_denied';
  if (agentsStatus === 403) return 'feature_disabled';
  if (agentsStatus !== null) return 'error';
  return 'ok';
}
