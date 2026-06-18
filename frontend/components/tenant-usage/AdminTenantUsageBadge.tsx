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
    ? 'border-red-500/30 bg-red-500/10 text-red-300'
    : approaching
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
      : 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300';

  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium ${tone}`}>
      <Icon className="h-3.5 w-3.5" />
      <span>{usage.usage_percent.toFixed(1)}%</span>
      <Gauge className="h-3.5 w-3.5 opacity-70" />
    </div>
  );
}
