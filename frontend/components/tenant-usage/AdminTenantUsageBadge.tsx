import { AlertTriangle, CheckCircle2, Gauge } from 'lucide-react';

import type { TenantUsage } from '@/lib/api/tenants';
import { isUsageLimitStatus } from '@/lib/tenant-plans';

type AdminTenantUsageBadgeProps = {
  usage?: TenantUsage;
};

export function AdminTenantUsageBadge({ usage }: AdminTenantUsageBadgeProps) {
  if (!usage) {
    return null;
  }

  const limitReached = isUsageLimitStatus(usage.usage_status);
  const approaching = usage.usage_status === 'approaching_limit';
  const Icon = limitReached || approaching ? AlertTriangle : CheckCircle2;
  const tone = limitReached
    ? 'border-red-300 bg-red-50 text-red-600 dark:border-red-700 dark:bg-red-950/30 dark:text-red-400'
    : approaching
      ? 'border-amber-300 bg-amber-50 text-amber-600 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-400'
      : 'border-emerald-300 bg-emerald-50 text-emerald-600 dark:border-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-400';

  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>
      <Icon className="h-3.5 w-3.5" />
      <span>{usage.usage_percent.toFixed(1)}%</span>
      <Gauge className="h-3.5 w-3.5 opacity-70" />
    </div>
  );
}
