'use client';

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';
import type { AgentDistribution } from '@/lib/api/dashboard';

interface AgentDistributionChartProps {
  data: AgentDistribution[];
}

export function AgentDistributionChart({ data }: AgentDistributionChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-white/10 bg-zinc-900/40">
        <p className="text-sm text-zinc-500">No hay datos de agentes.</p>
      </div>
    );
  }

  // Sort by count descending and take top 5-10
  const sortedData = [...data].sort((a, b) => b.count - a.count).slice(0, 10);

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-5">
      <h3 className="mb-6 text-lg font-medium text-zinc-200">Llamadas por Agente</h3>
      <div className="h-[250px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={sortedData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" vertical={false} />
            <XAxis 
              dataKey="agent_name" 
              stroke="#a1a1aa" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis 
              stroke="#a1a1aa" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '8px' }}
              itemStyle={{ color: '#e4e4e7' }}
              cursor={{ fill: '#27272a' }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Llamadas" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
