import type { TenantPlanKey } from '@/lib/api/tenants';
import { TENANT_PLAN_OPTIONS, getTenantPlanOption } from '@/lib/tenant-plans';

type TenantPlanFieldsProps = {
  planKey: TenantPlanKey;
  includedMinutes: string;
  pricePerMinuteUsd: string;
  disabled?: boolean;
  onPlanKeyChange: (planKey: TenantPlanKey) => void;
  onIncludedMinutesChange: (value: string) => void;
  onPricePerMinuteUsdChange: (value: string) => void;
};

export function TenantPlanFields({
  planKey,
  includedMinutes,
  pricePerMinuteUsd,
  disabled = false,
  onPlanKeyChange,
  onIncludedMinutesChange,
  onPricePerMinuteUsdChange,
}: TenantPlanFieldsProps) {
  const selectedPlan = getTenantPlanOption(planKey);
  const fieldsLocked = !selectedPlan.editable;

  const handlePlanChange = (value: string) => {
    const nextPlanKey = value as TenantPlanKey;
    const nextPlan = getTenantPlanOption(nextPlanKey);
    onPlanKeyChange(nextPlanKey);
    onIncludedMinutesChange(String(nextPlan.includedMinutes));
    onPricePerMinuteUsdChange(nextPlan.pricePerMinuteUsd.toFixed(2));
  };

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <div className="sm:col-span-3">
        <label className="mb-1.5 block text-sm font-medium text-zinc-400 dark:text-zinc-300">
          Plan comercial
        </label>
        <select
          value={planKey}
          onChange={(event) => handlePlanChange(event.target.value)}
          disabled={disabled}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
        >
          {TENANT_PLAN_OPTIONS.map((plan) => (
            <option key={plan.key} value={plan.key}>
              {plan.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-zinc-400 dark:text-zinc-300">
          Minutos incluidos
        </label>
        <input
          type="number"
          min={2000}
          step={1}
          value={includedMinutes}
          onChange={(event) => onIncludedMinutesChange(event.target.value)}
          disabled={disabled || fieldsLocked}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
        />
      </div>

      <div>
        <label className="mb-1.5 block text-sm font-medium text-zinc-400 dark:text-zinc-300">
          USD/min
        </label>
        <input
          type="number"
          min={planKey === 'enterprise' ? 0.14 : undefined}
          max={planKey === 'enterprise' ? 0.15 : undefined}
          step={0.01}
          value={pricePerMinuteUsd}
          onChange={(event) => onPricePerMinuteUsdChange(event.target.value)}
          disabled={disabled || fieldsLocked}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-800 dark:text-zinc-100 dark:focus:border-cyan-400 dark:focus:ring-cyan-400"
        />
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2.5 dark:border-zinc-700 dark:bg-zinc-900">
        <p className="text-xs text-zinc-500 dark:text-zinc-400">Politica</p>
        <p className="mt-1 text-sm text-zinc-300 dark:text-zinc-200">
          {fieldsLocked ? 'Valores bloqueados' : 'Enterprise configurable'}
        </p>
      </div>
    </div>
  );
}
