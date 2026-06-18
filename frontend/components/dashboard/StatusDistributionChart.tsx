'use client';

import { useTheme } from 'next-themes';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import type { DashboardStatusDistributionResponse } from '@/lib/api/dashboard';
import { useEffect, useState } from 'react';

interface StatusDistributionChartProps {
  data: DashboardStatusDistributionResponse;
}

const COLORS: Record<string, string> = {
  completed: '#10b981', // emerald-500
  failed: '#ef4444',    // red-500
  no_answer: '#f59e0b', // amber-500
  in_progress: '#3b82f6', // blue-500
  voicemail: '#8b5cf6', // violet-500
};

const LABELS: Record<string, string> = {
  completed: 'Completada',
  failed: 'Fallida',
  no_answer: 'Sin Respuesta',
  in_progress: 'En Progreso',
  voicemail: 'Buzón de Voz',
};

export function StatusDistributionChart({ data }: StatusDistributionChartProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = resolvedTheme === 'dark' || !mounted;

  if (!data?.items || !Array.isArray(data.items) || data.items.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-border bg-card">
        <p className="text-sm text-muted-foreground">No hay datos de estados.</p>
      </div>
    );
  }

  if (!mounted) {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-6 text-lg font-medium text-foreground">Distribución de Estados</h3>
        <div className="h-[250px] w-full animate-pulse rounded-md bg-muted/40" />
      </div>
    );
  }

  const formattedData = data.items.map(item => ({
    name: LABELS[item.key] || item.label || item.key,
    value: item.calls,
    color: COLORS[item.key] || '#a1a1aa'
  }));

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h3 className="mb-6 text-lg font-medium text-foreground">Distribución de Estados</h3>
      <div className="h-[250px] w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
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
              contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', borderRadius: '8px' }}
              itemStyle={{ color: isDark ? '#e4e4e7' : '#18181b' }}
            />
            <Legend verticalAlign="bottom" height={36} iconType="circle" />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
