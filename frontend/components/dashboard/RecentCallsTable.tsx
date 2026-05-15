'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import type { DashboardRecentCallsResponse } from '@/lib/api/dashboard';

interface RecentCallsTableProps {
  data: DashboardRecentCallsResponse;
}

const MONTHS_ES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

function formatCallDateTime(value?: string | null) {
  if (!value) return 'N/A';

  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!match) return value;

  const [, year, month, day, hour, minute] = match;
  const monthLabel = MONTHS_ES[Number(month) - 1];
  if (!monthLabel) return value;

  return `${day} ${monthLabel} ${year}, ${hour}:${minute}`;
}

export function RecentCallsTable({ data }: RecentCallsTableProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const items = Array.isArray(data?.items) ? data.items : [];
  const { page = 1, page_size = 10, total = 0 } = data ?? {};
  const totalPages = Math.max(1, Math.ceil(total / page_size));
  const currentStart = total === 0 ? 0 : (page - 1) * page_size + 1;
  const currentEnd = Math.min(page * page_size, total);

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;

    const params = new URLSearchParams(searchParams.toString());
    params.set('page', newPage.toString());
    router.push(`${pathname}?${params.toString()}`);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'answered':
        return <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-500 ring-1 ring-inset ring-emerald-500/20">Contestada</span>;
      case 'unanswered':
        return <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-500 ring-1 ring-inset ring-amber-500/20">No contestada</span>;
      case 'failed':
        return <span className="inline-flex items-center rounded-full bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/20">Fallida</span>;
      case 'in_progress':
        return <span className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-500 ring-1 ring-inset ring-blue-500/20">En curso</span>;
      case 'rejected':
        return <span className="inline-flex items-center rounded-full bg-orange-500/10 px-2 py-1 text-xs font-medium text-orange-500 ring-1 ring-inset ring-orange-500/20">Rechazada</span>;
      case 'cancelled':
        return <span className="inline-flex items-center rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border">Cancelada</span>;
      default:
        return <span className="inline-flex items-center rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border">{status}</span>;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="p-5 border-b border-border flex flex-row items-center justify-between">
        <h3 className="text-lg font-medium text-foreground">Llamadas Recientes</h3>
        <span className="text-xs text-muted-foreground">Total: {total}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-muted-foreground">
          <thead className="bg-muted/50 text-xs uppercase text-muted-foreground">
            <tr>
              <th scope="col" className="px-6 py-4 font-medium">ID</th>
              <th scope="col" className="px-6 py-4 font-medium">Fecha</th>
              <th scope="col" className="px-6 py-4 font-medium">Agente</th>
              <th scope="col" className="px-6 py-4 font-medium">Duración (s)</th>
              <th scope="col" className="px-6 py-4 font-medium">Estado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-12 text-center text-sm text-muted-foreground">
                  No hay llamadas recientes.
                </td>
              </tr>
            ) : items.map((call) => (
              <tr key={call.id} className="transition-colors hover:bg-muted/50">
                <td className="whitespace-nowrap px-6 py-4 font-mono text-xs text-muted-foreground">
                  {call.id.slice(0, 8)}...
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-foreground">
                  {formatCallDateTime(call.started_at)}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-foreground">
                  {call.agent_name || 'Desconocido'}
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-foreground">
                  {Math.round(call.duration_seconds ?? 0)}s
                </td>
                <td className="whitespace-nowrap px-6 py-4">
                  {getStatusBadge(call.status)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-3 border-t border-border px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground">
          Mostrando <span className="font-medium text-foreground">{currentStart}</span>-<span className="font-medium text-foreground">{currentEnd}</span> de <span className="font-medium text-foreground">{total}</span>
        </p>
        <div className="flex items-center justify-between gap-3 sm:justify-end">
          <p className="text-sm text-muted-foreground">
            Página <span className="font-medium text-foreground">{page}</span> de <span className="font-medium text-foreground">{totalPages}</span>
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
              aria-label="Página anterior"
              type="button"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages}
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
              aria-label="Página siguiente"
              type="button"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
