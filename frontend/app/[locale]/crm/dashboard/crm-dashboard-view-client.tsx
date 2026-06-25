'use client';

import React, { useState, useTransition } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { CrmDashboardResponse } from '@/types/crm';
import { CrmMetricCard } from '@/components/crm/CrmMetricCard';
import {
  Target,
  TrendingUp,
  CheckSquare,
  ShieldAlert,
  Calendar,
  Layers,
  PhoneCall,
  AlertCircle,
  ArrowRight,
  Filter,
  RefreshCw,
} from 'lucide-react';
import Link from 'next/link';

type CrmDashboardViewClientProps = {
  initialData: CrmDashboardResponse;
  locale: string;
};

const STAGE_TRANSLATIONS: Record<string, string> = {
  new: 'Nuevo',
  contacted: 'Contactado',
  connected: 'Conectado',
  qualified: 'Calificado',
  scheduled: 'Agendado',
  follow_up: 'En seguimiento',
  not_interested: 'No Interesado',
  won: 'Ganado',
  lost: 'Perdido',
};

export function CrmDashboardViewClient({
  initialData,
  locale,
}: CrmDashboardViewClientProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  // Filters State
  const [range, setRange] = useState(searchParams.get('range') || '30d');
  const [source, setSource] = useState(searchParams.get('source') || '');
  const [campaign, setCampaign] = useState(searchParams.get('campaign') || '');
  const [dateFrom, setDateFrom] = useState(searchParams.get('date_from') || '');
  const [dateTo, setDateTo] = useState(searchParams.get('date_to') || '');

  const data = initialData;

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    startTransition(() => {
      const params = new URLSearchParams();
      if (range) params.set('range', range);
      if (source) params.set('source', source);
      if (campaign) params.set('campaign', campaign);
      if (range === 'custom') {
        if (!dateFrom || !dateTo) {
          setError('El rango personalizado requiere fecha de inicio y fin.');
          return;
        }
        params.set('date_from', dateFrom);
        params.set('date_to', dateTo);
      }
      router.push(`/${locale}/crm/dashboard?${params.toString()}`);
    });
  };

  const handleResetFilters = () => {
    setRange('30d');
    setSource('');
    setCampaign('');
    setDateFrom('');
    setDateTo('');
    setError(null);
    startTransition(() => {
      router.push(`/${locale}/crm/dashboard`);
    });
  };

  return (
    <div className="flex flex-col gap-8">
      {/* Toast Alert Feedback */}
      {(isPending || error) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span>Actualizando métricas...</span>
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <ShieldAlert className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}
        </div>
      )}

      {/* Header Section */}
      <section className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Dashboard Comercial CRM
          </h2>
          <p className="text-sm text-muted-foreground">
            Rendimiento del embudo de ventas, conversión de campañas y leads pendientes.
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground bg-muted/40 border border-border/50 rounded-lg px-3 py-1.5 self-start sm:self-center">
          <Calendar className="h-3.5 w-3.5 text-violet-500" />
          <span>
            Período: {data.period.from} a {data.period.to} ({data.period.range})
          </span>
        </div>
      </section>

      {/* Filters Form */}
      <section className="rounded-xl border border-border bg-card/65 p-5 shadow-xs">
        <form onSubmit={handleApplyFilters} className="flex flex-col gap-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider pb-2 border-b border-border/60">
            <Filter className="h-4 w-4 text-violet-500" />
            <span>Filtrar Dashboard</span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            {/* Range */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="range" className="text-xs font-medium text-muted-foreground">
                Rango de Fecha
              </label>
              <select
                id="range"
                value={range}
                onChange={(e) => setRange(e.target.value)}
                className="w-full h-9 rounded-md border border-input bg-card px-3 py-1.5 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-hidden focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="today">Hoy</option>
                <option value="7d">Últimos 7 días</option>
                <option value="30d">Últimos 30 días</option>
                <option value="month">Este Mes</option>
                <option value="custom">Rango Personalizado</option>
              </select>
            </div>

            {/* Custom From */}
            {range === 'custom' && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="dateFrom" className="text-xs font-medium text-muted-foreground">
                  Desde
                </label>
                <input
                  type="date"
                  id="dateFrom"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-card px-3 py-1.5 text-sm"
                />
              </div>
            )}

            {/* Custom To */}
            {range === 'custom' && (
              <div className="flex flex-col gap-1.5">
                <label htmlFor="dateTo" className="text-xs font-medium text-muted-foreground">
                  Hasta
                </label>
                <input
                  type="date"
                  id="dateTo"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-card px-3 py-1.5 text-sm"
                />
              </div>
            )}

            {/* Source */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="source" className="text-xs font-medium text-muted-foreground">
                Fuente (source)
              </label>
              <input
                type="text"
                id="source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="Ej. landing, facebook"
                className="w-full h-9 rounded-md border border-input bg-card px-3 py-1.5 text-sm"
              />
            </div>

            {/* Campaign */}
            <div className="flex flex-col gap-1.5">
              <label htmlFor="campaign" className="text-xs font-medium text-muted-foreground">
                Campaña (campaign)
              </label>
              <input
                type="text"
                id="campaign"
                value={campaign}
                onChange={(e) => setCampaign(e.target.value)}
                placeholder="Ej. demo-crm"
                className="w-full h-9 rounded-md border border-input bg-card px-3 py-1.5 text-sm"
              />
            </div>

            {/* Action buttons */}
            <div className="flex items-end gap-2 sm:col-span-3 lg:col-span-1">
              <button
                type="submit"
                disabled={isPending}
                className="flex-1 inline-flex h-9 items-center justify-center rounded-md bg-violet-600 px-4 text-sm font-semibold text-white shadow-sm hover:bg-violet-500 disabled:opacity-50 transition"
              >
                Aplicar
              </button>
              <button
                type="button"
                onClick={handleResetFilters}
                disabled={isPending}
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition"
                title="Restablecer filtros"
              >
                <RefreshCw className="h-4 w-4" />
              </button>
            </div>
          </div>
        </form>
      </section>

      {/* KPIs Grid */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CrmMetricCard
          title="Leads Ingresados"
          value={data.kpis.total_leads}
          icon={Layers}
          subtext="Total de leads en el período"
          iconClassName="bg-blue-500/10 text-blue-500"
        />
        <CrmMetricCard
          title="Leads Abiertos"
          value={data.kpis.open_leads}
          icon={Target}
          subtext={`${data.kpis.new_leads} nuevos • ${data.kpis.follow_up_leads} en seguimiento`}
          iconClassName="bg-violet-500/10 text-violet-500"
        />
        <CrmMetricCard
          title="Acción Comercial"
          value={data.kpis.leads_with_next_action}
          icon={TrendingUp}
          subtext="Leads con próxima acción definida"
          iconClassName="bg-emerald-500/10 text-emerald-500"
        />
        <CrmMetricCard
          title="Tareas Pendientes"
          value={data.kpis.pending_tasks}
          icon={CheckSquare}
          subtext={`${data.kpis.overdue_tasks} tareas vencidas`}
          iconClassName={
            data.kpis.overdue_tasks > 0
              ? 'bg-red-500/10 text-red-500 animate-pulse'
              : 'bg-amber-500/10 text-amber-500'
          }
        />
      </section>

      {/* Funnel & Conversion rates */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Embudo */}
        <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs lg:col-span-2 flex flex-col gap-6">
          <div className="flex items-center gap-2 font-bold text-foreground text-sm uppercase tracking-wider border-b border-border/60 pb-3">
            <Layers className="h-5 w-5 text-violet-500" />
            <span>Embudo Comercial (Funnel)</span>
          </div>

          <div className="flex flex-col gap-4">
            {data.funnel.map((item, idx) => {
              const maxCount = Math.max(...data.funnel.map((f) => f.count), 1);
              const percentageWidth = Math.max((item.count / maxCount) * 100, 2);

              const barColors = [
                'from-blue-600 to-blue-500',
                'from-indigo-600 to-indigo-500',
                'from-violet-600 to-violet-500',
                'from-purple-600 to-purple-500',
                'from-pink-600 to-pink-500',
                'from-emerald-600 to-emerald-500',
              ];
              const colorClass = barColors[idx % barColors.length];

              return (
                <div key={item.stage} className="flex items-center gap-4">
                  <div className="w-28 text-sm font-medium text-foreground truncate" title={item.label}>
                    {item.label}
                  </div>
                  <div className="flex-1 bg-muted/30 rounded-full h-8 overflow-hidden relative border border-border/20 shadow-inner">
                    <div
                      className={`h-full bg-gradient-to-r ${colorClass} rounded-full transition-all duration-500 flex items-center justify-end pr-4 text-xs font-bold text-white shadow-md`}
                      style={{ width: `${percentageWidth}%` }}
                    >
                      {item.count > 0 && <span>{item.count}</span>}
                    </div>
                    {item.count === 0 && (
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-medium">
                        0 leads
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Call Metrics */}
        <div className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
          <div className="flex items-center gap-2 font-bold text-foreground text-sm uppercase tracking-wider border-b border-border/60 pb-3">
            <PhoneCall className="h-5 w-5 text-violet-500" />
            <span>Métricas de Llamadas</span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="p-3 bg-muted/20 rounded-lg">
              <span className="text-[10px] text-muted-foreground font-semibold block uppercase">
                Total Llamadas
              </span>
              <span className="text-xl font-extrabold text-foreground">{data.calls.total_calls}</span>
            </div>
            <div className="p-3 bg-muted/20 rounded-lg">
              <span className="text-[10px] text-muted-foreground font-semibold block uppercase">
                Atendidas
              </span>
              <span className="text-xl font-extrabold text-emerald-500">{data.calls.answered_calls}</span>
            </div>
            <div className="p-3 bg-muted/20 rounded-lg">
              <span className="text-[10px] text-muted-foreground font-semibold block uppercase">
                No Atendidas
              </span>
              <span className="text-xl font-extrabold text-amber-500">{data.calls.unanswered_calls}</span>
            </div>
            <div className="p-3 bg-muted/20 rounded-lg">
              <span className="text-[10px] text-muted-foreground font-semibold block uppercase">
                Fallidas/Buzón
              </span>
              <span className="text-xl font-extrabold text-indigo-500">
                {data.calls.failed_calls + data.calls.voicemail_calls}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4 pt-4 border-t border-border/40">
            <div>
              <span className="text-xs text-muted-foreground block">Duración Promedio</span>
              <span className="text-sm font-bold text-foreground">
                {Math.floor(data.calls.average_duration_seconds / 60)}m{' '}
                {Math.round(data.calls.average_duration_seconds % 60)}s
              </span>
            </div>
            <div>
              <span className="text-xs text-muted-foreground block">Billed Minutes</span>
              <span className="text-sm font-bold text-foreground">
                {data.calls.total_billed_minutes.toFixed(1)} min
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Conversion Cards */}
      <section className="flex flex-col gap-3">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Tasas de Conversión
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
          <div className="rounded-xl border border-border bg-card/65 p-4 text-center shadow-xs">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Tasa Contacto
            </span>
            <p className="mt-2 text-2xl font-extrabold text-blue-500">{data.conversion.contact_rate}%</p>
            <p className="mt-1 text-[10px] text-muted-foreground">contactados / total</p>
          </div>
          <div className="rounded-xl border border-border bg-card/65 p-4 text-center shadow-xs">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Tasa Conexión
            </span>
            <p className="mt-2 text-2xl font-extrabold text-indigo-500">{data.conversion.connection_rate}%</p>
            <p className="mt-1 text-[10px] text-muted-foreground">conectados / contactados</p>
          </div>
          <div className="rounded-xl border border-border bg-card/65 p-4 text-center shadow-xs">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Tasa Calificación
            </span>
            <p className="mt-2 text-2xl font-extrabold text-violet-500">{data.conversion.qualification_rate}%</p>
            <p className="mt-1 text-[10px] text-muted-foreground">calificados / conectados</p>
          </div>
          <div className="rounded-xl border border-border bg-card/65 p-4 text-center shadow-xs">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Tasa Agendamiento
            </span>
            <p className="mt-2 text-2xl font-extrabold text-pink-500">{data.conversion.schedule_rate}%</p>
            <p className="mt-1 text-[10px] text-muted-foreground">agendados / calificados</p>
          </div>
          <div className="rounded-xl border border-border bg-card/65 p-4 text-center shadow-xs">
            <span className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground block">
              Tasa Cierre
            </span>
            <p className="mt-2 text-2xl font-extrabold text-emerald-500">{data.conversion.win_rate}%</p>
            <p className="mt-1 text-[10px] text-muted-foreground">ganados / agendados</p>
          </div>
        </div>
      </section>

      {/* Sources & Campaigns performance tables */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sources table */}
        <div className="rounded-xl border border-border bg-card/65 p-5 shadow-xs flex flex-col gap-4">
          <div className="text-sm font-bold text-foreground uppercase tracking-wider border-b border-border/60 pb-2">
            Rendimiento por Fuente (Source)
          </div>
          {data.sources.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No hay datos de fuentes disponibles.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-xs font-semibold text-muted-foreground uppercase">
                    <th className="py-2 px-3">Fuente</th>
                    <th className="py-2 px-3 text-center">Total Leads</th>
                    <th className="py-2 px-3 text-center">Calificados</th>
                    <th className="py-2 px-3 text-center">Agendados</th>
                    <th className="py-2 px-3 text-center">Ganados</th>
                    <th className="py-2 px-3 text-right">Conv. Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.sources.map((src) => (
                    <tr key={src.source} className="border-b border-border/40 hover:bg-muted/5 transition">
                      <td className="py-2 px-3 font-medium text-foreground">{src.source}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{src.total_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{src.qualified_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{src.scheduled_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{src.won_leads}</td>
                      <td className="py-2 px-3 text-right font-semibold text-violet-500">
                        {src.conversion_rate}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Campaigns table */}
        <div className="rounded-xl border border-border bg-card/65 p-5 shadow-xs flex flex-col gap-4">
          <div className="text-sm font-bold text-foreground uppercase tracking-wider border-b border-border/60 pb-2">
            Rendimiento por Campaña (Campaign)
          </div>
          {data.campaigns.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No hay datos de campañas disponibles.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border/60 text-xs font-semibold text-muted-foreground uppercase">
                    <th className="py-2 px-3">Campaña</th>
                    <th className="py-2 px-3 text-center">Total Leads</th>
                    <th className="py-2 px-3 text-center">Calificados</th>
                    <th className="py-2 px-3 text-center">Agendados</th>
                    <th className="py-2 px-3 text-center">Ganados</th>
                    <th className="py-2 px-3 text-right">Conv. Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.campaigns.map((camp) => (
                    <tr key={camp.campaign} className="border-b border-border/40 hover:bg-muted/5 transition">
                      <td className="py-2 px-3 font-medium text-foreground">{camp.campaign}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{camp.total_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{camp.qualified_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{camp.scheduled_leads}</td>
                      <td className="py-2 px-3 text-center text-muted-foreground">{camp.won_leads}</td>
                      <td className="py-2 px-3 text-right font-semibold text-violet-500">
                        {camp.conversion_rate}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Pending Actions human intervention required */}
      <section className="rounded-xl border border-border bg-card/65 p-6 shadow-xs flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-border/60 pb-3">
          <div className="flex items-center gap-2 font-bold text-foreground text-sm uppercase tracking-wider">
            <AlertCircle className="h-5 w-5 text-red-500" />
            <span>Leads que Requieren Acción Humana</span>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 bg-red-500/10 text-red-500 rounded-full border border-red-500/15">
            {data.pending_actions.length} pendientes
          </span>
        </div>

        {data.pending_actions.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            No hay acciones pendientes en este momento. ¡Buen trabajo!
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-xs font-semibold text-muted-foreground uppercase">
                  <th className="py-3 px-4">Contacto</th>
                  <th className="py-3 px-4">Etapa</th>
                  <th className="py-3 px-4">Próxima Acción / Motivo</th>
                  <th className="py-3 px-4">Fuente / Campaña</th>
                  <th className="py-3 px-4">Fecha</th>
                  <th className="py-3 px-4 text-right">Acción</th>
                </tr>
              </thead>
              <tbody>
                {data.pending_actions.map((action) => (
                  <tr key={action.lead_id} className="border-b border-border/40 hover:bg-muted/10 transition">
                    <td className="py-3 px-4 font-semibold text-foreground">{action.contact_name}</td>
                    <td className="py-3 px-4">
                      <span className="text-xs font-medium px-2 py-0.5 rounded bg-violet-500/10 text-violet-500 border border-violet-500/20">
                        {STAGE_TRANSLATIONS[action.stage] || action.stage}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground font-medium">
                      {action.next_action || 'Revisión manual requerida (contactado sin conectar)'}
                    </td>
                    <td className="py-3 px-4 text-xs text-muted-foreground">
                      <span className="bg-muted px-1.5 py-0.5 rounded">{action.source || 'Sin fuente'}</span>
                      {action.campaign && (
                        <span className="ml-1 bg-muted px-1.5 py-0.5 rounded">{action.campaign}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-xs text-muted-foreground">
                      {new Date(action.updated_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Link
                        href={`/${locale}/crm/leads/${action.lead_id}`}
                        className="inline-flex items-center gap-1 text-xs font-bold text-violet-500 hover:text-violet-600 transition"
                      >
                        Atender <ArrowRight className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
