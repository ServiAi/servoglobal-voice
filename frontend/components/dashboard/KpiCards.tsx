import { Activity, Clock, DollarSign, PhoneCall, PhoneOff, CheckCircle } from 'lucide-react';
import type { DashboardKpisResponse } from '@/lib/api/dashboard';

interface KpiCardsProps {
  data: DashboardKpisResponse;
}

export function KpiCards({ data }: KpiCardsProps) {
  const numberFormatter = new Intl.NumberFormat('es-CO');
  const formatNumber = (value: number | undefined) => numberFormatter.format(value ?? 0);
  const formatPercent = (value: number | undefined) => `${(value ?? 0).toFixed(1)}%`;

  const kpis = [
    {
      title: 'Llamadas Totales',
      value: formatNumber(data?.calls_total),
      icon: <PhoneCall className="h-5 w-5 text-cyan-500" />,
      description: 'Volumen total del periodo'
    },
    {
      title: 'Contestadas',
      value: formatNumber(data?.calls_answered),
      icon: <CheckCircle className="h-5 w-5 text-emerald-500" />,
      description: 'Conectadas exitosamente'
    },
    {
      title: 'No Contestadas',
      value: formatNumber(data?.calls_unanswered),
      icon: <PhoneOff className="h-5 w-5 text-destructive" />,
      description: 'Sin respuesta registrada'
    },
    {
      title: 'Tasa de Éxito',
      value: formatPercent(data?.answer_rate),
      icon: <CheckCircle className="h-5 w-5 text-violet-500" />,
      description: 'Contestadas sobre cerradas'
    },
    {
      title: 'Duración Total',
      value: `${numberFormatter.format(Math.round((data?.total_duration_seconds ?? 0) / 60))} min`,
      icon: <Clock className="h-5 w-5 text-amber-500" />,
      description: 'Suma de duraciones'
    },
    {
      title: 'Promedio Duración',
      value: `${Math.round(data?.avg_duration_seconds ?? 0)} s`,
      icon: <Clock className="h-5 w-5 text-amber-500" />,
      description: 'Por llamada conectada'
    },
    {
      title: 'Minutos Facturados',
      value: formatNumber(Math.round(data?.billed_minutes ?? 0)),
      icon: <DollarSign className="h-5 w-5 text-emerald-500" />,
      description: 'Total facturable'
    },
    {
      title: 'Activas',
      value: formatNumber(data?.active_calls),
      icon: <Activity className="h-5 w-5 text-blue-500" />,
      description: 'En curso ahora'
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
