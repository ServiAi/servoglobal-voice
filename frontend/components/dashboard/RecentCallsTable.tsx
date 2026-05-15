import { format, parseISO } from 'date-fns';
import { es } from 'date-fns/locale';
import type { DashboardRecentCallsResponse } from '@/lib/api/dashboard';

interface RecentCallsTableProps {
  data: DashboardRecentCallsResponse;
}

export function RecentCallsTable({ data }: RecentCallsTableProps) {
  if (!data?.items || !Array.isArray(data.items) || data.items.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-xl border border-border bg-card">
        <p className="text-sm text-muted-foreground">No hay llamadas recientes.</p>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="inline-flex items-center rounded-full bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-500 ring-1 ring-inset ring-emerald-500/20">Completada</span>;
      case 'failed':
        return <span className="inline-flex items-center rounded-full bg-destructive/10 px-2 py-1 text-xs font-medium text-destructive ring-1 ring-inset ring-destructive/20">Fallida</span>;
      case 'no_answer':
        return <span className="inline-flex items-center rounded-full bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-500 ring-1 ring-inset ring-amber-500/20">Sin Respuesta</span>;
      case 'in_progress':
        return <span className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-1 text-xs font-medium text-blue-500 ring-1 ring-inset ring-blue-500/20">En Progreso</span>;
      default:
        return <span className="inline-flex items-center rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground ring-1 ring-inset ring-border">{status}</span>;
    }
  };

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="p-5 border-b border-border">
        <h3 className="text-lg font-medium text-foreground">Llamadas Recientes</h3>
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
            {data.items.map((call) => (
              <tr key={call.id} className="transition-colors hover:bg-muted/50">
                <td className="whitespace-nowrap px-6 py-4 font-mono text-xs text-muted-foreground">
                  {call.id.slice(0, 8)}...
                </td>
                <td className="whitespace-nowrap px-6 py-4 text-foreground">
                  {(() => {
                    try {
                      return call.started_at ? format(parseISO(call.started_at), "dd MMM yyyy, HH:mm", { locale: es }) : 'N/A';
                    } catch (e) {
                      return call.started_at || 'N/A';
                    }
                  })()}
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
    </div>
  );
}
