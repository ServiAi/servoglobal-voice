import { AlertTriangle, DollarSign, Gauge, PackageCheck } from 'lucide-react';
import type { ReactNode } from 'react';

import type { TenantUsage } from '@/lib/api/tenants';
import { isUsageLimitStatus } from '@/lib/tenant-plans';

type TenantUsageCardProps = {
  usage: TenantUsage;
};

const numberFormatter = new Intl.NumberFormat('es-CO', {
  maximumFractionDigits: 2,
});

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

function statusLabel(status: string) {
  switch (status) {
    case 'approaching_limit':
      return 'Cerca del limite';
    case 'limit_reached':
      return 'Limite alcanzado';
    case 'over_limit':
      return 'Sobre limite';
    case 'suspended_usage_limit':
      return 'Suspendido por limite';
    default:
      return 'Normal';
  }
}

export function TenantUsageCard({ usage }: TenantUsageCardProps) {
  const progress = Math.min(Math.max(usage.usage_percent, 0), 100);
  const limitReached = isUsageLimitStatus(usage.usage_status);
  const approaching = usage.usage_status === 'approaching_limit';
  const progressColor = limitReached
    ? 'bg-red-500'
    : approaching
      ? 'bg-amber-400'
      : 'bg-cyan-500';

  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-primary">
            Consumo del paquete
          </p>
          <h2 className="mt-1 text-xl font-semibold text-foreground">
            {usage.plan.plan_name}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {numberFormatter.format(usage.plan.included_minutes)} minutos incluidos a{' '}
            {currencyFormatter.format(usage.plan.price_per_minute_usd)} / min
          </p>
        </div>
        <div
          className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-semibold ${
            limitReached
              ? 'bg-red-500/10 text-red-400'
              : approaching
                ? 'bg-amber-500/10 text-amber-400'
                : 'bg-emerald-500/10 text-emerald-400'
          }`}
        >
          {limitReached || approaching ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : (
            <PackageCheck className="h-3.5 w-3.5" />
          )}
          {statusLabel(usage.usage_status)}
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Uso actual</span>
          <span className="font-medium text-foreground">
            {usage.usage_percent.toFixed(1)}%
          </span>
        </div>
        <div className="h-3 overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full ${progressColor}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-4">
        <Metric
          icon={<Gauge className="h-4 w-4 text-cyan-500" />}
          label="Usados"
          value={`${numberFormatter.format(usage.minutes_used)} min`}
        />
        <Metric
          icon={<Gauge className="h-4 w-4 text-emerald-500" />}
          label="Restantes"
          value={`${numberFormatter.format(Math.max(usage.minutes_remaining, 0))} min`}
        />
        <Metric
          icon={<DollarSign className="h-4 w-4 text-amber-500" />}
          label="Gasto"
          value={currencyFormatter.format(usage.amount_spent_usd)}
        />
        <Metric
          icon={<PackageCheck className="h-4 w-4 text-violet-500" />}
          label="Periodo"
          value={new Date(usage.plan.billing_period_end).toLocaleDateString('es-CO')}
        />
      </div>
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/40 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <p className="text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}
