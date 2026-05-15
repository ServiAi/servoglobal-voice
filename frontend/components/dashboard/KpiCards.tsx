import { PhoneCall, Clock, CheckCircle, DollarSign } from 'lucide-react';
import type { KpiData } from '@/lib/api/dashboard';

interface KpiCardsProps {
  data: KpiData;
}

export function KpiCards({ data }: KpiCardsProps) {
  const kpis = [
    {
      title: 'Llamadas Totales',
      value: (data?.total_calls ?? 0).toLocaleString(),
      icon: <PhoneCall className="h-5 w-5 text-cyan-400" />,
      description: 'Volumen total del periodo'
    },
    {
      title: 'Minutos Consumidos',
      value: Math.round(data?.total_minutes ?? 0).toLocaleString(),
      icon: <Clock className="h-5 w-5 text-emerald-400" />,
      description: `Promedio: ${Math.round(data?.avg_duration_seconds ?? 0)}s/llamada`
    },
    {
      title: 'Tasa de Éxito',
      value: `${((data?.success_rate ?? 0) * 100).toFixed(1)}%`,
      icon: <CheckCircle className="h-5 w-5 text-violet-400" />,
      description: 'Llamadas completadas'
    },
    {
      title: 'Costo Promedio',
      value: `$${(data?.avg_cost ?? 0).toFixed(3)}`,
      icon: <DollarSign className="h-5 w-5 text-amber-400" />,
      description: 'Por llamada'
    }
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-8">
      {kpis.map((kpi, index) => (
        <div
          key={index}
          className="relative overflow-hidden rounded-xl border border-white/10 bg-zinc-900/40 p-5 backdrop-blur-sm transition-all hover:border-white/20 hover:bg-zinc-900/60"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-zinc-400">{kpi.title}</p>
            <div className="rounded-full bg-white/5 p-2">{kpi.icon}</div>
          </div>
          <div className="mt-4">
            <h3 className="text-3xl font-semibold tracking-tight text-zinc-100">
              {kpi.value}
            </h3>
            <p className="mt-1 text-xs text-zinc-500">{kpi.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
