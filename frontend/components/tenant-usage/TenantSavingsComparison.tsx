import { BadgeDollarSign } from 'lucide-react';

import type { TenantSavingsComparison } from '@/lib/api/tenants';

type TenantSavingsComparisonProps = {
  comparison: TenantSavingsComparison;
};

const currencyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

function formatPrice(value: number | null) {
  if (value === null) {
    return 'Manual';
  }
  return `${currencyFormatter.format(value)} / min`;
}

function formatSavings(value: number | null, percent: number | null) {
  if (value === null || percent === null) {
    return 'Requiere precio';
  }
  return `${currencyFormatter.format(value)} (${percent.toFixed(1)}%)`;
}

export function TenantSavingsComparison({ comparison }: TenantSavingsComparisonProps) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium uppercase text-primary">
            Comparativa de ahorro
          </p>
          <h2 className="mt-1 text-lg font-semibold text-foreground">
            ServiGlobal IA vs proveedores externos
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Costo ServiGlobal actual: {currencyFormatter.format(comparison.serviglobal_cost_usd)}
          </p>
        </div>
        <BadgeDollarSign className="h-5 w-5 text-emerald-500" />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="pb-2 pr-4 font-medium">Proveedor</th>
              <th className="pb-2 pr-4 font-medium">Precio</th>
              <th className="pb-2 pr-4 font-medium">Costo estimado</th>
              <th className="pb-2 pr-4 font-medium">Ahorro</th>
              <th className="pb-2 font-medium">Fuente</th>
            </tr>
          </thead>
          <tbody>
            {comparison.providers.map((provider) => (
              <tr key={provider.provider_key} className="border-b border-border/60">
                <td className="py-3 pr-4 font-medium text-foreground">
                  {provider.provider_name}
                </td>
                <td className="py-3 pr-4 text-muted-foreground">
                  {formatPrice(provider.provider_price_per_minute_usd)}
                </td>
                <td className="py-3 pr-4 text-muted-foreground">
                  {provider.estimated_cost_usd === null
                    ? 'No publico'
                    : currencyFormatter.format(provider.estimated_cost_usd)}
                </td>
                <td className="py-3 pr-4 text-emerald-500">
                  {formatSavings(
                    provider.estimated_savings_usd,
                    provider.estimated_savings_percent
                  )}
                </td>
                <td className="py-3 text-xs text-muted-foreground">
                  {provider.price_source}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
