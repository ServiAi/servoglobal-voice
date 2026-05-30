import type { TenantPlanKey } from '@/lib/api/tenants';

export type TenantPlanOption = {
  key: TenantPlanKey;
  label: string;
  includedMinutes: number;
  pricePerMinuteUsd: number;
  editable: boolean;
};

export const TENANT_PLAN_OPTIONS: TenantPlanOption[] = [
  {
    key: 'web_conversion',
    label: 'Plan Web Conversion',
    includedMinutes: 2000,
    pricePerMinuteUsd: 0.16,
    editable: false,
  },
  {
    key: 'voice_cloud_pbx',
    label: 'Plan Voice Cloud / PBX',
    includedMinutes: 2000,
    pricePerMinuteUsd: 0.18,
    editable: false,
  },
  {
    key: 'enterprise',
    label: 'Enterprise',
    includedMinutes: 2000,
    pricePerMinuteUsd: 0.14,
    editable: true,
  },
];

export function getTenantPlanOption(planKey: TenantPlanKey) {
  return TENANT_PLAN_OPTIONS.find((plan) => plan.key === planKey) ?? TENANT_PLAN_OPTIONS[0];
}

export function isUsageLimitStatus(status: string | undefined) {
  return status === 'limit_reached' || status === 'over_limit' || status === 'suspended_usage_limit';
}
