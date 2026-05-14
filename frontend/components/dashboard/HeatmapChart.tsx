'use client';

import { useMemo } from 'react';
import type { HeatmapPoint } from '@/lib/api/dashboard';

interface HeatmapChartProps {
  data: HeatmapPoint[];
}

const DAYS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

export function HeatmapChart({ data }: HeatmapChartProps) {
  const { grid, maxCount } = useMemo(() => {
    let max = 0;
    const map = new Map<string, number>();
    
    data.forEach((p) => {
      if (p.call_count > max) max = p.call_count;
      map.set(`${p.day_of_week}-${p.hour_of_day}`, p.call_count);
    });

    return { grid: map, maxCount: max };
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-white/10 bg-zinc-900/40">
        <p className="text-sm text-zinc-500">No hay datos de calor.</p>
      </div>
    );
  }

  // Function to determine color intensity based on value relative to maxCount
  const getIntensityColor = (count: number) => {
    if (count === 0) return 'bg-zinc-800/30';
    const ratio = count / maxCount;
    if (ratio < 0.2) return 'bg-cyan-900/40';
    if (ratio < 0.4) return 'bg-cyan-800/60';
    if (ratio < 0.6) return 'bg-cyan-600/80';
    if (ratio < 0.8) return 'bg-cyan-500';
    return 'bg-cyan-400';
  };

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/40 p-5 overflow-x-auto">
      <h3 className="mb-6 text-lg font-medium text-zinc-200">Mapa de Calor (Volumen)</h3>
      <div className="min-w-[600px]">
        {/* Header - Hours */}
        <div className="flex ml-10 mb-2">
          {HOURS.map((hour) => (
            <div key={hour} className="flex-1 text-center text-[10px] text-zinc-500">
              {hour}
            </div>
          ))}
        </div>
        
        {/* Grid - Days */}
        <div className="flex flex-col gap-1">
          {DAYS.map((day, dIdx) => (
            <div key={day} className="flex items-center">
              <div className="w-10 text-xs font-medium text-zinc-400">{day}</div>
              <div className="flex flex-1 gap-1">
                {HOURS.map((hour) => {
                  const count = grid.get(`${dIdx}-${hour}`) || 0;
                  return (
                    <div
                      key={`${dIdx}-${hour}`}
                      title={`${day} a las ${hour}:00 - ${count} llamadas`}
                      className={`flex-1 rounded-[2px] transition-colors hover:ring-1 hover:ring-white h-6 ${getIntensityColor(count)}`}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="mt-4 flex items-center justify-end gap-2 text-xs text-zinc-500">
          <span>Menos</span>
          <div className="flex gap-1">
            <div className="h-3 w-3 rounded-sm bg-zinc-800/30" />
            <div className="h-3 w-3 rounded-sm bg-cyan-900/40" />
            <div className="h-3 w-3 rounded-sm bg-cyan-800/60" />
            <div className="h-3 w-3 rounded-sm bg-cyan-600/80" />
            <div className="h-3 w-3 rounded-sm bg-cyan-500" />
            <div className="h-3 w-3 rounded-sm bg-cyan-400" />
          </div>
          <span>Más</span>
        </div>
      </div>
    </div>
  );
}
