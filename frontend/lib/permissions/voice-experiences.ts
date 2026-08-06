import type { MeProfile } from '@/lib/api/me';
import type { VoiceExperienceGateState } from '@/types/voice-experiences';

const READ_ROLES = new Set(['platform_admin', 'tenant_admin', 'tenant_analyst', 'tenant_viewer']);
const WRITE_ROLES = new Set(['platform_admin', 'tenant_admin']);

function hasInternalPlatformAccess(profile: Pick<MeProfile, 'role' | 'is_internal'>) {
  return profile.role !== 'platform_admin' || profile.is_internal;
}

export function canReadVoiceExperiences(profile: Pick<MeProfile, 'role' | 'is_internal'>) {
  return READ_ROLES.has(profile.role) && hasInternalPlatformAccess(profile);
}

export function canEditVoiceExperiences(profile: Pick<MeProfile, 'role' | 'is_internal'>) {
  return WRITE_ROLES.has(profile.role) && hasInternalPlatformAccess(profile);
}

export function resolveVoiceExperienceGateState({
  canRead,
  experiencesStatus,
  agentsStatus,
  agentCount,
}: {
  canRead: boolean;
  experiencesStatus: number | null;
  agentsStatus: number | null;
  agentCount: number;
}): VoiceExperienceGateState {
  if (!canRead) return 'access_denied';
  if (experiencesStatus === 403) return 'feature_disabled';
  if (agentsStatus === 404) return 'integration_disabled';
  if (experiencesStatus !== null || agentsStatus !== null) return 'error';
  return agentCount === 0 ? 'no_agents' : 'ok';
}
