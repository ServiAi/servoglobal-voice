import type { CrmVoiceCapacityMetrics } from '@/types/crm';

export type VoiceCapacityStatus = 'normal' | 'high' | 'saturated' | 'unavailable';

export function getVoiceCapacityStatus(capacity: CrmVoiceCapacityMetrics): VoiceCapacityStatus {
  if (
    !capacity.configured ||
    capacity.route_status !== 'active' ||
    capacity.provision_status !== 'active'
  ) {
    return 'unavailable';
  }
  if (capacity.utilization_percent >= 100) return 'saturated';
  if (capacity.utilization_percent >= 80) return 'high';
  return 'normal';
}

export function canManageVoiceCapacity(role: string): boolean {
  return role === 'platform_admin' || role === 'tenant_admin';
}
