'use client';

import { useState, type FormEvent } from 'react';
import { Loader2, Save } from 'lucide-react';

import type { TenantPlanPayload, TenantUsage } from '@/lib/api/tenants';
import { TenantPlanFields } from '@/components/tenant-usage/TenantPlanFields';

type PlanUpdateFormProps = {
  usage: TenantUsage;
  saving: boolean;
  onSubmit: (payload: TenantPlanPayload) => Promise<void>;
};

export function PlanUpdateForm({ usage, saving, onSubmit }: PlanUpdateFormProps) {
  const [planKey, setPlanKey] = useState(usage.plan.plan_key);
  const [includedMinutes, setIncludedMinutes] = useState(
    String(Math.round(usage.plan.included_minutes))
  );
  const [pricePerMinuteUsd, setPricePerMinuteUsd] = useState(
    usage.plan.price_per_minute_usd.toFixed(2)
  );
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    const minutes = Number.parseFloat(includedMinutes);
    const price = Number.parseFloat(pricePerMinuteUsd);
    if (planKey === 'enterprise') {
      if (!Number.isFinite(minutes) || minutes < 2000) {
        setError('Enterprise requiere minimo 2000 minutos.');
        return;
      }
      if (!Number.isFinite(price) || price < 0.14 || price > 0.15) {
        setError('Enterprise requiere precio entre 0.14 y 0.15 USD/min.');
        return;
      }
    }
    await onSubmit({
      plan_key: planKey,
      included_minutes: minutes,
      price_per_minute_usd: price,
    });
  };

  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4">
        <p className="text-sm font-medium uppercase text-primary">Plan comercial</p>
        <h2 className="mt-1 text-lg font-semibold text-foreground">
          Actualizar plan del tenant
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <TenantPlanFields
          planKey={planKey}
          includedMinutes={includedMinutes}
          pricePerMinuteUsd={pricePerMinuteUsd}
          disabled={saving}
          onPlanKeyChange={setPlanKey}
          onIncludedMinutesChange={setIncludedMinutes}
          onPricePerMinuteUsdChange={setPricePerMinuteUsd}
        />

        {error && (
          <p className="rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar plan
        </button>
      </form>
    </section>
  );
}
