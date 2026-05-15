'use client';

import {
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Line
} from 'recharts';
import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import type { DashboardTrendsResponse } from '@/lib/api/dashboard';

interface TrendsChartProps {
  data: DashboardTrendsResponse;
}

export function TrendsChart({ data }: TrendsChartProps) {
  if (!data?.series || !Array.isArray(data.series) || data.series.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-white/10 bg-zinc-900/40">
        <p className="text-sm text-zinc-500">No hay datos de tendencias para este periodo.</p>
      </div>
    );
  }

  // Format dates for the X axis
  const formattedData = data.series.map(item => {
    let displayDate = item.date;
    try {
      if (item.date) {
        displayDate = format(parseISO(item.date), 'dd MMM', { locale: es });
      }
    } catch (e) {
      // Ignore parse error
    }
    
    const answerRate = item.calls_total > 0 ? (item.calls_answered / item.calls_total) : 0;
    
    return {
      ...item,
      displayDate,
      total_calls: item.calls_total,
      successPercent: Math.round(answerRate * 100)
    };
  });

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-5">
      <h3 className="mb-6 text-lg font-medium text-zinc-200">Tendencia de Llamadas</h3>
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={formattedData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" vertical={false} />
            <XAxis 
              dataKey="displayDate" 
              stroke="#a1a1aa" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis 
              yAxisId="left"
              stroke="#a1a1aa" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <YAxis 
              yAxisId="right"
              orientation="right"
              stroke="#a1a1aa" 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={10}
              tickFormatter={(val) => `${val}%`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: '#18181b', borderColor: '#3f3f46', borderRadius: '8px' }}
              itemStyle={{ color: '#e4e4e7' }}
              labelStyle={{ color: '#a1a1aa', marginBottom: '4px' }}
            />
            <Area 
              yAxisId="left"
              type="monotone" 
              dataKey="total_calls" 
              name="Llamadas"
              stroke="#22d3ee" 
              strokeWidth={2}
              fillOpacity={1} 
              fill="url(#colorCalls)" 
            />
            <Line 
              yAxisId="right"
              type="monotone" 
              dataKey="successPercent" 
              name="% Éxito"
              stroke="#a78bfa" 
              strokeWidth={2}
              dot={{ r: 4, fill: '#a78bfa' }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
