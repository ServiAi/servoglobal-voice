'use client';

import { useTheme } from 'next-themes';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import type { DashboardAgentDistributionResponse } from '@/lib/api/dashboard';
import { useEffect, useState } from 'react';

interface AgentDistributionChartProps {
  data: DashboardAgentDistributionResponse;
}

export function AgentDistributionChart({ data }: AgentDistributionChartProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = resolvedTheme === 'dark' || !mounted;

  if (!data?.items || !Array.isArray(data.items) || data.items.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-border bg-card">
        <p className="text-sm text-muted-foreground">No hay datos de agentes.</p>
      </div>
    );
  }

  if (!mounted) {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="mb-6 text-lg font-medium text-foreground">Llamadas por Agente</h3>
        <div className="h-[250px] w-full animate-pulse rounded-md bg-muted/40" />
      </div>
    );
  }

  // Sort by calls descending and take top 10
  const sortedData = [...data.items].sort((a, b) => b.calls - a.calls).slice(0, 10);

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h3 className="mb-6 text-lg font-medium text-foreground">Llamadas por Agente</h3>
      <div className="h-[250px] w-full">
        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
          <BarChart data={sortedData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#3f3f46" : "#e4e4e7"} vertical={false} />
            <XAxis 
              dataKey="agent_name" 
              stroke={isDark ? "#a1a1aa" : "#71717a"} 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis 
              stroke={isDark ? "#a1a1aa" : "#71717a"} 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <Tooltip
              contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', borderRadius: '8px' }}
              itemStyle={{ color: isDark ? '#e4e4e7' : '#18181b' }}
              cursor={{ fill: isDark ? '#27272a' : '#f4f4f5' }}
            />
            <Bar dataKey="calls" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Llamadas" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
