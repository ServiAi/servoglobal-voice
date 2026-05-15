'use client';

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import type { DashboardStatusDistributionResponse } from '@/lib/api/dashboard';

interface StatusDistributionChartProps {
  data: DashboardStatusDistributionResponse;
}

const COLORS: Record<string, string> = {
  completed: '#10b981', // emerald-500
  failed: '#ef4444',    // red-500
  no_answer: '#f59e0b', // amber-500
  in_progress: '#3b82f6', // blue-500
};

const LABELS: Record<string, string> = {
  completed: 'Completada',
  failed: 'Fallida',
  no_answer: 'Sin Respuesta',
  in_progress: 'En Progreso'
};

export function StatusDistributionChart({ data }: StatusDistributionChartProps) {
  if (!data?.items || !Array.isArray(data.items) || data.items.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-white/10 bg-zinc-900/40">
        <p className="text-sm text-zinc-500">No hay datos de estados.</p>
      </div>
    );
  }

  const formattedData = data.items.map(item => ({
    name: LABELS[item.key] || item.label || item.key,
    value: item.calls,
    color: COLORS[item.key] || '#a1a1aa'
  }));

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-5">
      <h3 className="mb-6 text-lg font-medium text-zinc-200">Distribución de Estados</h3>
      <div className="h-[250px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={formattedData}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={5}
              dataKey="value"
              stroke="none"
            >
              {formattedData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip 
              contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '8px' }}
              itemStyle={{ color: '#e4e4e7' }}
            />
            <Legend verticalAlign="bottom" height={36} iconType="circle" />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
