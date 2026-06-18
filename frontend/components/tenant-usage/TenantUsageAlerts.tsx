import { AlertTriangle, CheckCircle2 } from 'lucide-react';

import type { TenantUsageAlert } from '@/lib/api/tenants';

type TenantUsageAlertsProps = {
  alerts: TenantUsageAlert[];
};

function alertLabel(alertType: string) {
  switch (alertType) {
    case 'warning_80':
      return 'Warning 80%';
    case 'warning_90':
      return 'Warning 90%';
    case 'limit_reached':
      return 'Limite alcanzado';
    default:
      return alertType;
  }
}

export function TenantUsageAlerts({ alerts }: TenantUsageAlertsProps) {
  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-sm font-medium uppercase text-primary">Alertas</p>
          <h2 className="mt-1 text-lg font-semibold text-foreground">
            Consumo y limites
          </h2>
        </div>
        {alerts.length === 0 ? (
          <CheckCircle2 className="h-5 w-5 text-emerald-500" />
        ) : (
          <AlertTriangle className="h-5 w-5 text-amber-500" />
        )}
      </div>

      {alerts.length === 0 ? (
        <p className="rounded-lg border border-border bg-background/40 p-3 text-sm text-muted-foreground">
          Sin alertas activas para el periodo actual.
        </p>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="rounded-lg border border-amber-300 bg-amber-50 p-3 dark:border-amber-700 dark:bg-amber-950/30"
            >
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
                  {alertLabel(alert.alert_type)}
                </p>
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  {alert.threshold_percent.toFixed(0)}%
                </span>
              </div>
              <p className="mt-1 text-xs text-amber-600 dark:text-amber-300">{alert.message}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
