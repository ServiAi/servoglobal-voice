'use client';

import { useTheme } from 'next-themes';
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
import { useEffect, useState } from 'react';

interface TrendsChartProps {
  data: DashboardTrendsResponse;
}

export function TrendsChart({ data }: TrendsChartProps) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const isDark = resolvedTheme === 'dark' || !mounted;

  if (!data?.series || !Array.isArray(data.series) || data.series.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-border bg-card">
        <p className="text-sm text-muted-foreground">No hay datos de tendencias para este periodo.</p>
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
    <div className="rounded-xl border border-border bg-card p-5">
      <h3 className="mb-6 text-lg font-medium text-foreground">Tendencia de Llamadas</h3>
      <div className="h-[300px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={formattedData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22d3ee" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#3f3f46" : "#e4e4e7"} vertical={false} />
            <XAxis 
              dataKey="displayDate" 
              stroke={isDark ? "#a1a1aa" : "#71717a"} 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dy={10}
            />
            <YAxis 
              yAxisId="left"
              stroke={isDark ? "#a1a1aa" : "#71717a"} 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={-10}
            />
            <YAxis 
              yAxisId="right"
              orientation="right"
              stroke={isDark ? "#a1a1aa" : "#71717a"} 
              fontSize={12} 
              tickLine={false}
              axisLine={false}
              dx={10}
              tickFormatter={(val) => `${val}%`}
            />
            <Tooltip
              contentStyle={{ backgroundColor: isDark ? '#18181b' : '#ffffff', borderColor: isDark ? '#3f3f46' : '#e4e4e7', borderRadius: '8px' }}
              itemStyle={{ color: isDark ? '#e4e4e7' : '#18181b' }}
              labelStyle={{ color: isDark ? '#a1a1aa' : '#71717a', marginBottom: '4px' }}
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
