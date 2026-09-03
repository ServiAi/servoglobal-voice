import Link from 'next/link';
import { Activity, Gauge, Settings } from 'lucide-react';
import type { CrmDashboardResponse } from '@/types/crm';
import { formatCrmDate } from '@/components/crm/lead-workspace/crm-format';
import { getVoiceCapacityStatus } from '@/lib/permissions/voice-capacity';

type Props = { data: CrmDashboardResponse; locale: string; canManageCapacity: boolean };

export function VoiceCapacityPanel({ data, locale, canManageCapacity }: Props) {
  const capacity = data.voice_capacity;
  const copy = locale === 'en' ? {
    title: 'Outbound call capacity (SIP)', subtitle: 'Simultaneous channels used by callback calls; this does not represent minutes or conversation results.', active: 'Active now', limit: 'Simultaneous limit', available: 'Available slots', rejected: 'Period rejections', reconciled: 'Reconciled closures', forced: 'Forced releases', utilization: 'Utilization', route: 'Route', provision: 'Provisioning', manage: 'Manage capacity', noEvents: 'No saturation or recovery events in this period.', history: 'Saturations and recoveries', filters: 'Current occupancy is live. Counters and history use the selected period; source and campaign filters do not affect SIP capacity.', normal: 'Normal', high: 'High capacity', saturated: 'Saturated', unavailable: 'Unavailable', notConfigured: 'Not configured', capacityReached: 'Capacity reached', reconciledEvent: 'Call reconciled', forcedEvent: 'Forced release', resulting: 'Resulting status' }
    : {
    title: 'Capacidad de llamadas salientes (SIP)', subtitle: 'Canales simultáneos usados por las llamadas callback; no representa minutos ni resultados de conversación.', active: 'Activas ahora', limit: 'Límite simultáneo', available: 'Cupos disponibles', rejected: 'Rechazos del período', reconciled: 'Cierres reconciliados', forced: 'Liberaciones forzadas', utilization: 'Utilización', route: 'Ruta', provision: 'Aprovisionamiento', manage: 'Administrar capacidad', noEvents: 'No hubo saturaciones ni recuperaciones en este período.', history: 'Saturaciones y recuperaciones', filters: 'La ocupación actual es en vivo. Los contadores y el historial usan el período seleccionado; los filtros de fuente y campaña no afectan la capacidad SIP.', normal: 'Normal', high: 'Capacidad alta', saturated: 'Saturada', unavailable: 'No disponible', notConfigured: 'Sin configurar', capacityReached: 'Capacidad alcanzada', reconciledEvent: 'Llamada reconciliada', forcedEvent: 'Liberación forzada', resulting: 'Estado resultante' };
  const status = getVoiceCapacityStatus(capacity);
  const statusLabel = { normal: copy.normal, high: copy.high, saturated: copy.saturated, unavailable: copy.unavailable }[status];
  const tone = { normal: 'bg-emerald-500', high: 'bg-amber-500', saturated: 'bg-destructive', unavailable: 'bg-muted-foreground/40' }[status];
  const badge = { normal: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300', high: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300', saturated: 'border-destructive/30 bg-destructive/10 text-destructive', unavailable: 'border-border bg-muted text-muted-foreground' }[status];
  const eventLabels = { capacity_reached: copy.capacityReached, reconciled: copy.reconciledEvent, forced_release: copy.forcedEvent };
  const operationalLabels: Record<string, string> = locale === 'en'
    ? { active: 'Active', inactive: 'Inactive', pending: 'Pending', failed: 'Failed', disabled: 'Disabled', completed: 'Completed', no_answer: 'No answer', busy: 'Busy', cancelled: 'Cancelled' }
    : { active: 'Activa', inactive: 'Inactiva', pending: 'Pendiente', failed: 'Fallida', disabled: 'Deshabilitada', completed: 'Completada', no_answer: 'Sin respuesta', busy: 'Ocupada', cancelled: 'Cancelada' };
  const statusText = (value: string | null | undefined) => value ? operationalLabels[value] ?? value : copy.notConfigured;

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card" aria-labelledby="voice-capacity-title">
      <header className="flex flex-col gap-4 border-b border-border p-4 sm:flex-row sm:items-start sm:justify-between sm:p-6">
        <div className="min-w-0">
          <h2 id="voice-capacity-title" className="flex items-center gap-2 text-base font-semibold">
            <Gauge className="size-4 shrink-0 text-primary" />
            {copy.title}
          </h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">{copy.subtitle}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <span className={`inline-flex items-center rounded-md border px-2.5 py-1 text-xs font-semibold ${badge}`}>{statusLabel}</span>
          {canManageCapacity ? (
            <Link
              href={`/${locale}/integrations/voice`}
              className="inline-flex min-h-9 items-center gap-2 rounded-md border border-border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Settings className="size-4" />
              {copy.manage}
            </Link>
          ) : null}
        </div>
      </header>
      <div className="p-4 sm:p-6">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          <Metric label={copy.active} value={capacity.active_calls} />
          <Metric label={copy.limit} value={capacity.max_concurrent_calls} />
          <Metric label={copy.available} value={capacity.available_slots} />
          <Metric label={copy.rejected} value={capacity.capacity_rejections} />
          <Metric label={copy.reconciled} value={capacity.reconciled_calls} />
          <Metric label={copy.forced} value={capacity.forced_releases} />
        </dl>
        <div className="mt-6 border-y border-border py-5">
          <div className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{copy.utilization}</span>
            <strong className="tabular-nums">{capacity.utilization_percent.toFixed(1)}%</strong>
          </div>
          <div
            className="mt-2 h-2.5 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label={copy.utilization}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.min(capacity.utilization_percent, 100)}
          >
            <div className={`h-full rounded-full transition-[width] ${tone}`} style={{ width: `${Math.min(capacity.utilization_percent, 100)}%` }} />
          </div>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <span>{copy.route}: <strong className="text-foreground">{statusText(capacity.route_status)}</strong></span>
            <span>{copy.provision}: <strong className="text-foreground">{statusText(capacity.provision_status)}</strong></span>
          </div>
        </div>
        <div className="mt-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <Activity className="size-4 text-primary" />
            {copy.history}
          </h3>
          {capacity.recent_events.length ? (
            <div className="mt-3 divide-y divide-border">
              {capacity.recent_events.map((event, index) => (
                <article key={`${event.occurred_at}-${event.event_type}-${index}`} className="grid gap-1 py-3 text-sm sm:grid-cols-[minmax(180px,1fr)_auto] sm:items-center">
                  <div>
                    <p className="font-medium">{eventLabels[event.event_type]}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {event.event_type === 'capacity_reached'
                        ? `${event.active_calls ?? 0} / ${event.max_concurrent_calls ?? 0}`
                        : event.resulting_status
                          ? `${copy.resulting}: ${statusText(event.resulting_status)}`
                          : null}
                    </p>
                  </div>
                  <time className="text-xs text-muted-foreground" dateTime={event.occurred_at}>{formatCrmDate(event.occurred_at)}</time>
                </article>
              ))}
            </div>
          ) : (
            <Empty text={copy.noEvents} />
          )}
        </div>
        <p className="mt-5 border-t border-border pt-4 text-xs leading-5 text-muted-foreground">{copy.filters}</p>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-semibold">{value}</dd>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="mt-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">{text}</div>;
}
