import { expect, test } from '@playwright/test';
import type { CrmVoiceCapacityMetrics } from '@/types/crm';
import {
  canManageVoiceCapacity,
  getVoiceCapacityStatus,
} from '@/app/[locale]/crm/dashboard/voice-capacity';

const capacity = (overrides: Partial<CrmVoiceCapacityMetrics> = {}): CrmVoiceCapacityMetrics => ({
  configured: true,
  route_status: 'active',
  provision_status: 'active',
  active_calls: 0,
  max_concurrent_calls: 3,
  available_slots: 3,
  utilization_percent: 0,
  capacity_rejections: 0,
  reconciled_calls: 0,
  forced_releases: 0,
  recent_events: [],
  ...overrides,
});

test('clasifica los estados operacionales de capacidad', () => {
  expect(getVoiceCapacityStatus(capacity({ utilization_percent: 79.9 }))).toBe('normal');
  expect(getVoiceCapacityStatus(capacity({ utilization_percent: 80 }))).toBe('high');
  expect(getVoiceCapacityStatus(capacity({ utilization_percent: 100 }))).toBe('saturated');
  expect(getVoiceCapacityStatus(capacity({ configured: false }))).toBe('unavailable');
  expect(getVoiceCapacityStatus(capacity({ route_status: 'inactive' }))).toBe('unavailable');
  expect(getVoiceCapacityStatus(capacity({ provision_status: 'pending' }))).toBe('unavailable');
});

test('limita la administración a roles administradores', () => {
  expect(canManageVoiceCapacity('platform_admin')).toBe(true);
  expect(canManageVoiceCapacity('tenant_admin')).toBe(true);
  expect(canManageVoiceCapacity('tenant_analyst')).toBe(false);
  expect(canManageVoiceCapacity('tenant_viewer')).toBe(false);
});
