import { PhoneCall, Clock, CheckCircle, DollarSign } from 'lucide-react';
import type { DashboardKpisResponse } from '@/lib/api/dashboard';

interface KpiCardsProps {
  data: DashboardKpisResponse;
}

export function KpiCards({ data }: KpiCardsProps) {
  const kpis = [
    {
      title: 'Llamadas Totales',
      value: (data?.calls_total ?? 0).toLocaleString(),
      icon: <PhoneCall className="h-5 w-5 text-cyan-500" />,
      description: 'Volumen total del periodo'
    },
    {
      title: 'Minutos Consumidos',
      value: Math.round(data?.billed_minutes ?? 0).toLocaleString(),
      icon: <Clock className="h-5 w-5 text-emerald-500" />,
      description: `Promedio: ${Math.round(data?.avg_duration_seconds ?? 0)}s/llamada`
    },
    {
      title: 'Tasa de Éxito',
      value: `${((data?.answer_rate ?? 0) * 100).toFixed(1)}%`,
      icon: <CheckCircle className="h-5 w-5 text-violet-500" />,
      description: 'Llamadas completadas'
    },
    {
      title: 'Costo Estimado',
      value: `$${((data?.billed_minutes ?? 0) * 0.05).toFixed(3)}`, // placeholder for avg cost
      icon: <DollarSign className="h-5 w-5 text-amber-500" />,
      description: 'Total facturado'
    }
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
      {kpis.map((kpi, index) => (
        <div
          key={index}
          className="relative overflow-hidden rounded-xl border border-border bg-card p-5 transition-all hover:border-primary/20 hover:bg-muted/50 shadow-sm"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">{kpi.title}</p>
            <div className="rounded-full bg-muted p-2">{kpi.icon}</div>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-semibold tracking-tight text-foreground">
              {kpi.value}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground">{kpi.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
