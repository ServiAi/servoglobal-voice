'use client';

import { useRouter, usePathname } from 'next/navigation';
import { useCallback, useState } from 'react';
import { Calendar, Search } from 'lucide-react';
import type { DashboardFilters as DashboardFilterValues } from '@/lib/api/dashboard';

type DashboardFiltersProps = {
  initialFilters?: DashboardFilterValues;
  initialQueryString?: string;
};

export function DashboardFilters({ initialFilters, initialQueryString = '' }: DashboardFiltersProps) {
  const router = useRouter();
  const pathname = usePathname();

  // Keep local state for the inputs
  const [from, setFrom] = useState(initialFilters?.from || '');
  const [to, setTo] = useState(initialFilters?.to || '');
  const [agentId, setAgentId] = useState(initialFilters?.agent_id || '');
  const [status, setStatus] = useState(initialFilters?.status || '');

  const createQueryString = useCallback(
    (params: Record<string, string>) => {
      const newSearchParams = new URLSearchParams(initialQueryString);

      Object.entries(params).forEach(([name, value]) => {
        if (value) {
          newSearchParams.set(name, value);
        } else {
          newSearchParams.delete(name);
        }
      });

      return newSearchParams.toString();
    },
    [initialQueryString]
  );

  const handleApply = (e: React.FormEvent) => {
    e.preventDefault();
    router.push(`${pathname}?${createQueryString({
      from,
      to,
      agent_id: agentId,
      status,
      page: ''
    })}`);
  };

  const handleReset = () => {
    setFrom('');
    setTo('');
    setAgentId('');
    setStatus('');
    router.push(pathname);
  };

  return (
    <div className="rounded-xl border border-white/10 bg-zinc-900/50 p-4 mb-8">
      <form onSubmit={handleApply} className="flex flex-wrap items-end gap-4">
        
        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label htmlFor="from" className="text-xs font-medium text-zinc-400">
            Fecha Desde
          </label>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="date"
              id="from"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-zinc-950 py-2 pl-10 pr-3 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label htmlFor="to" className="text-xs font-medium text-zinc-400">
            Fecha Hasta
          </label>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="date"
              id="to"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-zinc-950 py-2 pl-10 pr-3 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label htmlFor="agent_id" className="text-xs font-medium text-zinc-400">
            ID de Agente
          </label>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-500" />
            <input
              type="text"
              id="agent_id"
              placeholder="Todos los agentes"
              value={agentId}
              onChange={(e) => setAgentId(e.target.value)}
              className="w-full rounded-md border border-white/10 bg-zinc-950 py-2 pl-10 pr-3 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label htmlFor="status" className="text-xs font-medium text-zinc-400">
            Estado de Llamada
          </label>
          <select
            id="status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="w-full appearance-none rounded-md border border-white/10 bg-zinc-950 py-2 pl-3 pr-8 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
          >
            <option value="">Todos los estados</option>
            <option value="answered">Contestadas</option>
            <option value="unanswered">No contestadas</option>
            <option value="in_progress">En curso</option>
            <option value="failed">Fallidas</option>
            <option value="rejected">Rechazadas</option>
            <option value="cancelled">Canceladas</option>
          </select>
        </div>

        <div className="flex items-center gap-2 mt-2 sm:mt-0">
          <button
            type="submit"
            className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
          >
            Filtrar
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="rounded-md border border-white/10 px-4 py-2 text-sm font-medium text-zinc-300 transition hover:bg-white/5"
          >
            Limpiar
          </button>
        </div>

      </form>
    </div>
  );
}
