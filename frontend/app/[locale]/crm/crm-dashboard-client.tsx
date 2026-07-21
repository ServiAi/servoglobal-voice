'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckSquare2, PhoneCall, ShieldAlert, Target, TrendingUp, Users } from 'lucide-react';
import type { CrmDashboardResponse, CrmMetricsResponse, PipelineBoardResponse } from '@/types/crm';
import { changeCrmLeadStage } from '@/lib/api/crm';
import { CrmMetricCard } from '@/components/crm/CrmMetricCard';
import { CrmPipelineBoard } from '@/components/crm/CrmPipelineBoard';
import { CrmStageBadge } from '@/components/crm/shared/CrmStageBadge';
import { formatCrmDate, formatDuration } from '@/components/crm/lead-workspace/crm-format';

type Props = { initialMetrics: CrmMetricsResponse; initialBoard: PipelineBoardResponse; initialDashboard: CrmDashboardResponse; accessToken: string; locale: string };

export function CrmDashboardClient({ initialMetrics, initialBoard, initialDashboard, accessToken, locale }: Props) {
  const router = useRouter();
  const [view, setView] = useState<'home' | 'pipeline'>('home');
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleStageChange = async (leadId: string, stageKey: string) => {
    setError(null); setSuccess(null);
    try {
      const result = await changeCrmLeadStage(accessToken, leadId, { stage_key: stageKey, reason: 'Actualización rápida desde Kanban' });
      if (!result.ok) { setError(`Error al actualizar etapa: ${result.detail}`); return false; }
      setSuccess('Etapa actualizada con éxito.');
      startTransition(() => router.refresh());
      return true;
    } catch (caught) { console.error(caught); setError('Ocurrió un error inesperado.'); return false; }
  };

  return <div className="space-y-6">
    {(error || success || isPending) ? <div className="fixed bottom-4 left-4 right-4 z-50 max-w-sm rounded-lg border border-border bg-card p-4 shadow-lg sm:left-auto" role="status" aria-live="polite">{isPending ? <p className="text-sm text-muted-foreground">Actualizando Pipeline…</p> : null}{error ? <p className="flex gap-2 text-sm text-destructive"><ShieldAlert className="size-4 shrink-0" />{error}</p> : null}{success && !isPending ? <p className="text-sm text-emerald-600 dark:text-emerald-400">{success}</p> : null}</div> : null}

    <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between"><div><h1 className="text-2xl font-semibold tracking-tight text-foreground">Inicio CRM</h1><p className="mt-1 text-sm text-muted-foreground">Prioridades operativas y estado general del equipo comercial.</p></div><Link href={`/${locale}/crm/dashboard`} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-md border border-border px-4 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">Ver Rendimiento <ArrowRight className="size-4" /></Link></header>

    <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Vista de Inicio CRM"><button type="button" role="tab" aria-selected={view === 'home'} onClick={() => setView('home')} className="min-h-10 border-b-2 border-transparent px-4 text-sm font-medium text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring aria-selected:border-primary aria-selected:text-foreground">Resumen</button><button type="button" role="tab" aria-selected={view === 'pipeline'} onClick={() => setView('pipeline')} className="min-h-10 border-b-2 border-transparent px-4 text-sm font-medium text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring aria-selected:border-primary aria-selected:text-foreground">Pipeline</button></div>

    {view === 'pipeline' ? <CrmPipelineBoard boardData={initialBoard} locale={locale} onLeadStageChange={handleStageChange} /> : <CrmHomeSummary metrics={initialMetrics} board={initialBoard} dashboard={initialDashboard} locale={locale} onOpenPipeline={() => setView('pipeline')} />}
  </div>;
}

function CrmHomeSummary({ metrics, board, dashboard, locale, onOpenPipeline }: { metrics: CrmMetricsResponse; board: PipelineBoardResponse; dashboard: CrmDashboardResponse; locale: string; onOpenPipeline: () => void }) {
  const totalPipeline = board.stages.reduce((total, stage) => total + stage.count, 0);
  const maxStage = Math.max(...board.stages.map((stage) => stage.count), 1);
  return <div className="space-y-6">
    <section aria-labelledby="priorities-title" className="rounded-xl border border-border bg-card p-4 sm:p-6"><div className="flex items-center justify-between gap-3"><div><h2 id="priorities-title" className="text-base font-semibold">Acciones prioritarias</h2><p className="mt-1 text-sm text-muted-foreground">Elementos reales que requieren seguimiento.</p></div>{metrics.overdue_tasks > 0 ? <Link href={`/${locale}/crm/tasks`} className="rounded-full bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive">{metrics.overdue_tasks} tareas vencidas</Link> : null}</div>{dashboard.pending_actions.length ? <div className="mt-4 divide-y divide-border">{dashboard.pending_actions.slice(0, 5).map((item) => <article key={item.lead_id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="break-words text-sm font-semibold">{item.contact_name}</h3><CrmStageBadge stageKey={item.stage} stageName={item.stage} /></div><p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">{item.next_action || 'Seguimiento comercial pendiente'}</p><p className="mt-1 text-xs text-muted-foreground">Actualizado {formatCrmDate(item.updated_at)}</p></div><Link href={`/${locale}/crm/leads/${item.lead_id}`} className="inline-flex min-h-10 shrink-0 items-center justify-center rounded-md border border-border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">Abrir Lead</Link></article>)}</div> : <div className="mt-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No hay acciones comerciales pendientes en el período.</div>}</section>

    <section aria-label="Indicadores principales" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><CrmMetricCard title="Leads abiertos" value={metrics.open_leads} icon={Target} subtext={`De ${metrics.total_leads} Leads totales`} /><CrmMetricCard title="Conversión" value={`${metrics.conversion_rate.toFixed(1)}%`} icon={TrendingUp} tone="positive" subtext={`${metrics.won_leads} ganados`} /><CrmMetricCard title="Tareas pendientes" value={metrics.pending_tasks} icon={CheckSquare2} tone={metrics.overdue_tasks ? 'critical' : 'warning'} subtext={`${metrics.overdue_tasks} vencidas`} /><CrmMetricCard title="Llamadas atendidas" value={dashboard.calls.answered_calls} icon={PhoneCall} tone="positive" subtext={`De ${dashboard.calls.total_calls} llamadas`} /></section>

    <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]"><section className="rounded-xl border border-border bg-card p-4 sm:p-6"><div className="flex items-center justify-between gap-3"><div><h2 className="text-base font-semibold">Resumen del Pipeline</h2><p className="mt-1 text-sm text-muted-foreground">{totalPipeline} Leads según contadores del backend.</p></div><button type="button" onClick={onOpenPipeline} className="min-h-10 rounded-md border border-border px-3 text-sm font-medium outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring">Abrir Pipeline</button></div>{board.stages.length ? <div className="mt-5 space-y-3">{board.stages.map((stage) => <div key={stage.id}><div className="mb-1 flex items-center justify-between gap-3 text-sm"><CrmStageBadge stageKey={stage.key} stageName={stage.name} /><span className="font-semibold">{stage.count}</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${stage.count ? Math.max((stage.count / maxStage) * 100, 4) : 0}%` }} /></div></div>)}</div> : <p className="mt-5 text-sm text-muted-foreground">No hay etapas configuradas.</p>}</section><section className="rounded-xl border border-border bg-card p-4 sm:p-6"><h2 className="text-base font-semibold">Resumen de llamadas</h2><dl className="mt-4 grid grid-cols-2 gap-4"><Metric label="Total" value={dashboard.calls.total_calls} /><Metric label="Atendidas" value={dashboard.calls.answered_calls} /><Metric label="No atendidas" value={dashboard.calls.unanswered_calls} /><Metric label="Fallidas" value={dashboard.calls.failed_calls} /></dl><div className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground"><p>Duración promedio: <strong className="text-foreground">{formatDuration(dashboard.calls.average_duration_seconds) ?? 'Sin datos'}</strong></p><p className="mt-1">Minutos facturados: <strong className="text-foreground">{dashboard.calls.total_billed_minutes.toFixed(1)} min</strong></p></div></section></div>

    <section className="grid gap-3 sm:grid-cols-3" aria-label="Accesos rápidos"><QuickLink href={`/${locale}/crm/leads`} title="Leads" description="Buscar y gestionar contactos" icon={Users} /><QuickLink href={`/${locale}/crm/tasks`} title="Tareas" description="Revisar trabajo pendiente" icon={CheckSquare2} /><QuickLink href={`/${locale}/crm/dashboard`} title="Rendimiento" description="Analizar conversiones y llamadas" icon={TrendingUp} /></section>
  </div>;
}

function Metric({ label, value }: { label: string; value: string | number }) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-xl font-semibold">{value}</dd></div>; }
function QuickLink({ href, title, description, icon: Icon }: { href: string; title: string; description: string; icon: typeof Users }) { return <Link href={href} className="flex min-h-20 items-center gap-3 rounded-xl border border-border bg-card p-4 outline-none hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring"><span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="size-4" /></span><span><strong className="block text-sm">{title}</strong><span className="mt-1 block text-xs text-muted-foreground">{description}</span></span></Link>; }
