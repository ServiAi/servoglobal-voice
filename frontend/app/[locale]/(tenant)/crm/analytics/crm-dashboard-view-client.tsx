'use client';

import { useState, useTransition, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { CalendarDays, CheckSquare2, Filter, Layers3, RefreshCw, ShieldAlert, Target } from 'lucide-react';
import type { CrmDashboardResponse } from '@/types/crm';
import { CrmMetricCard } from '@/components/crm/CrmMetricCard';
import { CrmStageBadge } from '@/components/crm/shared/CrmStageBadge';
import { formatCrmDate } from '@/components/crm/lead-workspace/crm-format';
import { Button } from '@/components/ui/button';

type Props = { initialData: CrmDashboardResponse; locale: string };
type BreakdownItem = { name: string; total: number; qualified: number; scheduled: number; won: number; conversion: number };
const CONTROL = 'h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring';

export function CrmDashboardViewClient({ initialData: data, locale }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState(searchParams.get('range') || '30d');
  const [source, setSource] = useState(searchParams.get('source') || '');
  const [campaign, setCampaign] = useState(searchParams.get('campaign') || '');
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') || '');
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || '');
  const activeFilters = Number(range !== '30d') + Number(Boolean(source)) + Number(Boolean(campaign));

  const applyFilters = (event: FormEvent) => {
    event.preventDefault(); setError(null);
    if (range === 'custom' && (!dateFrom || !dateTo)) { setError('El rango personalizado requiere fecha de inicio y fin.'); return; }
    if (range === 'custom' && dateFrom > dateTo) { setError('La fecha inicial no puede ser posterior a la fecha final.'); return; }
    const params = new URLSearchParams();
    params.set('range', range);
    if (source.trim()) params.set('source', source.trim());
    if (campaign.trim()) params.set('campaign', campaign.trim());
    if (range === 'custom') { params.set('date_from', dateFrom); params.set('date_to', dateTo); }
    startTransition(() => router.push(`/${locale}/crm/analytics?${params}`));
  };
  const reset = () => { setRange('30d'); setSource(''); setCampaign(''); setDateFrom(''); setDateTo(''); setError(null); startTransition(() => router.push(`/${locale}/crm/analytics`)); };

  const sources = data.sources.map((item) => ({ name: item.source, total: item.total_leads, qualified: item.qualified_leads, scheduled: item.scheduled_leads, won: item.won_leads, conversion: item.conversion_rate }));
  const campaigns = data.campaigns.map((item) => ({ name: item.campaign, total: item.total_leads, qualified: item.qualified_leads, scheduled: item.scheduled_leads, won: item.won_leads, conversion: item.conversion_rate }));
  const conversion = [['Contacto', data.conversion.contact_rate, 'Contactados / Leads'], ['Conexión', data.conversion.connection_rate, 'Conectados / Contactados'], ['Calificación', data.conversion.qualification_rate, 'Calificados / Conectados'], ['Agendamiento', data.conversion.schedule_rate, 'Agendados / Calificados'], ['Cierre', data.conversion.win_rate, 'Ganados / Leads']] as const;
  const maxFunnel = Math.max(...data.funnel.map((item) => item.count), 1);

  return <div className="space-y-6">
    {(isPending || error) ? <div className="fixed bottom-4 left-4 right-4 z-50 max-w-sm rounded-lg border border-border bg-card p-4 shadow-lg sm:left-auto" role="status" aria-live="polite">{isPending ? <p className="text-sm text-muted-foreground">Actualizando rendimiento…</p> : null}{error ? <p className="flex gap-2 text-sm text-destructive"><ShieldAlert className="size-4 shrink-0" />{error}</p> : null}</div> : null}
    <header className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-semibold tracking-tight">Rendimiento</h1><p className="mt-1 text-sm text-muted-foreground">Análisis detallado de conversiones, llamadas, fuentes y campañas.</p></div><div className="flex items-center gap-2 text-xs text-muted-foreground"><CalendarDays className="size-4" /><span>{data.period.from} — {data.period.to}</span></div></header>

    <section className="rounded-xl border border-border bg-card p-4" aria-labelledby="filters-title"><div className="mb-3 flex items-center justify-between gap-3"><h2 id="filters-title" className="flex items-center gap-2 text-sm font-semibold"><Filter className="size-4 text-primary" />Filtros</h2><span className="text-xs text-muted-foreground">{activeFilters} activos</span></div><form onSubmit={applyFilters} className="grid gap-3 md:grid-cols-2 xl:grid-cols-[180px_1fr_1fr_auto]"><label><span className="mb-1 block text-xs text-muted-foreground">Período</span><select value={range} onChange={(event) => setRange(event.target.value)} className={CONTROL}><option value="today">Hoy</option><option value="7d">Últimos 7 días</option><option value="30d">Últimos 30 días</option><option value="month">Este mes</option><option value="custom">Personalizado</option></select></label><label><span className="mb-1 block text-xs text-muted-foreground">Fuente</span><input value={source} onChange={(event) => setSource(event.target.value)} placeholder="Ej. landing" className={CONTROL} /></label><label><span className="mb-1 block text-xs text-muted-foreground">Campaña</span><input value={campaign} onChange={(event) => setCampaign(event.target.value)} placeholder="Ej. demo-crm" className={CONTROL} /></label><div className="flex items-end gap-2"><Button type="submit" disabled={isPending} className="flex-1">Aplicar</Button><Button type="button" variant="outline" size="icon" onClick={reset} disabled={isPending} aria-label="Restablecer filtros"><RefreshCw className="size-4" /></Button></div>{range === 'custom' ? <div className="grid gap-3 md:col-span-2 md:grid-cols-2 xl:col-span-4"><label><span className="mb-1 block text-xs text-muted-foreground">Desde</span><input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} className={CONTROL} /></label><label><span className="mb-1 block text-xs text-muted-foreground">Hasta</span><input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} className={CONTROL} /></label></div> : null}</form></section>

    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Indicadores de rendimiento"><CrmMetricCard title="Leads del período" value={data.kpis.total_leads} icon={Layers3} subtext={`${data.kpis.new_leads} nuevos`} /><CrmMetricCard title="Leads abiertos" value={data.kpis.open_leads} icon={Target} subtext={`${data.kpis.follow_up_leads} en seguimiento`} /><CrmMetricCard title="Próxima acción" value={data.kpis.leads_with_next_action} icon={CalendarDays} tone="positive" subtext="Leads con acción definida" /><CrmMetricCard title="Tareas pendientes" value={data.kpis.pending_tasks} icon={CheckSquare2} tone={data.kpis.overdue_tasks ? 'critical' : 'warning'} subtext={`${data.kpis.overdue_tasks} vencidas`} /></section>

    {data.kpis.overdue_tasks || data.pending_actions.length ? <PendingActions data={data} locale={locale} /> : null}

    <section className="rounded-xl border border-border bg-card p-4 sm:p-6"><h2 className="text-base font-semibold">Embudo comercial</h2>{data.funnel.length ? <div className="mt-5 space-y-4">{data.funnel.map((item) => <div key={item.stage}><div className="mb-1 flex items-center justify-between gap-3"><CrmStageBadge stageKey={item.stage} stageName={item.label} /><span className="text-sm font-semibold">{item.count}</span></div><div className="h-7 overflow-hidden rounded-md border border-border bg-muted" aria-label={`${item.label}: ${item.count} Leads`}><div className="flex h-full items-center justify-end bg-primary px-2 text-xs font-semibold text-primary-foreground" style={{ width: item.count ? `${Math.max((item.count / maxFunnel) * 100, 5)}%` : 0 }}>{item.count ? item.count : null}</div></div></div>)}</div> : <Empty text="No hay datos de embudo para este período." />}</section>

    <section className="rounded-xl border border-border bg-card p-4 sm:p-6"><h2 className="text-base font-semibold">Tasas de conversión</h2><div className="mt-4 divide-y divide-border">{conversion.map(([label, value, context]) => <div key={label} className="grid gap-1 py-3 sm:grid-cols-[160px_100px_1fr] sm:items-center"><span className="text-sm font-medium">{label}</span><strong className="text-sm">{value.toFixed(1)}%</strong><span className="text-xs text-muted-foreground">{context}</span></div>)}</div></section>

    <div className="grid gap-6 xl:grid-cols-2"><Breakdown title="Rendimiento por fuente" empty="No hay fuentes para este período." items={sources} /><Breakdown title="Rendimiento por campaña" empty="No hay campañas para este período." items={campaigns} /></div>

    {!data.kpis.overdue_tasks && !data.pending_actions.length ? <PendingActions data={data} locale={locale} /> : null}
  </div>;
}

function PendingActions({ data, locale }: { data: CrmDashboardResponse; locale: string }) { return <section className="rounded-xl border border-border bg-card p-4 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-2"><h2 className="text-base font-semibold">Acciones humanas</h2>{data.kpis.overdue_tasks ? <Link href={`/${locale}/crm/tasks`} className="rounded-full bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive">{data.kpis.overdue_tasks} tareas vencidas</Link> : null}</div>{data.pending_actions.length ? <div className="mt-3 divide-y divide-border">{data.pending_actions.map((item) => <article key={item.lead_id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="text-sm font-semibold">{item.contact_name}</h3><CrmStageBadge stageKey={item.stage} stageName={item.stage} /></div><p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.next_action || 'Seguimiento comercial pendiente'}</p><p className="mt-1 text-xs text-muted-foreground">Actualizado {formatCrmDate(item.updated_at)}</p></div><Link href={`/${locale}/crm/leads/${item.lead_id}`} className="inline-flex min-h-10 shrink-0 items-center justify-center rounded-md border border-border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">Abrir Lead</Link></article>)}</div> : <Empty text="No hay acciones comerciales pendientes en el período." />}</section>; }

function Breakdown({ title, empty, items }: { title: string; empty: string; items: BreakdownItem[] }) { return <section className="rounded-xl border border-border bg-card p-4 sm:p-6"><h2 className="text-base font-semibold">{title}</h2>{items.length ? <><div className="mt-4 hidden overflow-x-auto md:block"><table className="w-full text-left text-sm"><thead><tr className="border-b border-border text-xs text-muted-foreground"><th className="py-2 font-medium">Nombre</th><th className="py-2 text-right font-medium">Total</th><th className="py-2 text-right font-medium">Calificados</th><th className="py-2 text-right font-medium">Agendados</th><th className="py-2 text-right font-medium">Ganados</th><th className="py-2 text-right font-medium">Conversión</th></tr></thead><tbody>{items.map((item) => <tr key={item.name} className="border-b border-border/60 last:border-0"><td className="max-w-44 break-words py-3 font-medium">{item.name}</td><td className="py-3 text-right">{item.total}</td><td className="py-3 text-right">{item.qualified}</td><td className="py-3 text-right">{item.scheduled}</td><td className="py-3 text-right">{item.won}</td><td className="py-3 text-right font-semibold">{item.conversion.toFixed(1)}%</td></tr>)}</tbody></table></div><div className="mt-4 space-y-3 md:hidden">{items.map((item) => <article key={item.name} className="rounded-lg border border-border p-3"><h3 className="break-words text-sm font-semibold">{item.name}</h3><dl className="mt-3 grid grid-cols-2 gap-3"><Metric label="Total" value={item.total} /><Metric label="Calificados" value={item.qualified} /><Metric label="Agendados" value={item.scheduled} /><Metric label="Ganados" value={item.won} /><Metric label="Conversión" value={`${item.conversion.toFixed(1)}%`} /></dl></article>)}</div></> : <Empty text={empty} />}</section>; }

function Metric({ label, value }: { label: string; value: string | number }) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-lg font-semibold">{value}</dd></div>; }
function Empty({ text }: { text: string }) { return <div className="mt-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">{text}</div>; }
