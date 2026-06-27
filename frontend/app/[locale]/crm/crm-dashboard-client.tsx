'use client';

import React, { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import type { CrmMetricsResponse, PipelineBoardResponse } from '@/types/crm';
import { CrmMetricCard } from '@/components/crm/CrmMetricCard';
import { CrmPipelineBoard } from '@/components/crm/CrmPipelineBoard';
import { changeCrmLeadStage } from '@/lib/api/crm';
import { Users, Target, TrendingUp, CheckSquare, ShieldAlert, Settings } from 'lucide-react';

type CrmDashboardClientProps = {
  initialMetrics: CrmMetricsResponse;
  initialBoard: PipelineBoardResponse;
  accessToken: string;
  locale: string;
};

export function CrmDashboardClient({
  initialMetrics,
  initialBoard,
  accessToken,
  locale,
}: CrmDashboardClientProps) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const handleStageChange = async (leadId: string, newStageKey: string) => {
    setError(null);
    setSuccessMsg(null);
    try {
      const res = await changeCrmLeadStage(accessToken, leadId, {
        stage_key: newStageKey,
        reason: 'Actualización rápida desde Kanban',
      });
      if (res.ok) {
        setSuccessMsg('Etapa actualizada con éxito.');
        startTransition(() => {
          router.refresh();
        });
        setTimeout(() => setSuccessMsg(null), 3000);
      } else {
        setError(`Error al actualizar etapa: ${res.detail}`);
      }
    } catch (err) {
      console.error(err);
      setError('Ocurrió un error inesperado.');
    }
  };

  return (
    <div className="flex flex-col gap-8">
      {/* Toast Alert Feedback */}
      {(error || successMsg || isPending) && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-lg border bg-card p-4 shadow-lg transition-all duration-300">
          {isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-violet-500 border-t-transparent" />
              <span>Actualizando embudo...</span>
            </div>
          )}
          {error && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <ShieldAlert className="h-4 w-4" />
              <span>{error}</span>
            </div>
          )}
          {successMsg && !isPending && (
            <div className="flex items-center gap-2 text-sm text-emerald-500">
              <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
              <span>{successMsg}</span>
            </div>
          )}
        </div>
      )}

      {/* Header Section */}
      <section className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b border-border pb-4">
        <div className="flex flex-col gap-2">
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Panel de Control CRM
          </h2>
          <p className="text-sm text-muted-foreground">
            Vista general del rendimiento comercial, pipeline y automatización.
          </p>
        </div>
        <div>
          <Link
            href={`/${locale}/crm/settings/integrations`}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 text-sm font-medium text-foreground shadow-xs transition hover:bg-accent hover:text-accent-foreground"
          >
            <Settings className="h-4 w-4" />
            Integraciones CRM
          </Link>
        </div>
      </section>

      {/* Metrics Row */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CrmMetricCard
          title="Total de Contactos"
          value={initialMetrics.total_contacts}
          icon={Users}
          subtext={`${initialMetrics.contact_completion_rate.toFixed(1)}% completado (tel/email)`}
          iconClassName="bg-blue-500/10 text-blue-500"
        />
        <CrmMetricCard
          title="Leads Abiertos"
          value={initialMetrics.open_leads}
          icon={Target}
          subtext={`De un total de ${initialMetrics.total_leads} leads`}
          iconClassName="bg-violet-500/10 text-violet-500"
        />
        <CrmMetricCard
          title="Tasa de Conversión"
          value={`${initialMetrics.conversion_rate.toFixed(1)}%`}
          icon={TrendingUp}
          subtext={`${initialMetrics.won_leads} ganados • ${initialMetrics.lost_leads} perdidos`}
          iconClassName="bg-emerald-500/10 text-emerald-500"
        />
        <CrmMetricCard
          title="Tareas Pendientes"
          value={initialMetrics.pending_tasks}
          icon={CheckSquare}
          subtext={`${initialMetrics.overdue_tasks} tareas vencidas`}
          iconClassName={initialMetrics.overdue_tasks > 0 ? "bg-red-500/10 text-red-500 animate-pulse" : "bg-amber-500/10 text-amber-500"}
        />
      </section>

      {/* Secondary Metrics Row */}
      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-border bg-card/65 p-4 text-center">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground">Nuevos Hoy</span>
          <p className="mt-1 text-lg font-bold text-foreground">{initialMetrics.leads_created_today}</p>
        </div>
        <div className="rounded-xl border border-border bg-card/65 p-4 text-center">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground">Esta Semana</span>
          <p className="mt-1 text-lg font-bold text-foreground">{initialMetrics.leads_created_this_week}</p>
        </div>
        <div className="rounded-xl border border-border bg-card/65 p-4 text-center">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground">Este Mes</span>
          <p className="mt-1 text-lg font-bold text-foreground">{initialMetrics.leads_created_this_month}</p>
        </div>
        <div className="rounded-xl border border-border bg-card/65 p-4 text-center">
          <span className="text-3xs uppercase tracking-wider text-muted-foreground">En Agenda / Citas</span>
          <p className="mt-1 text-lg font-bold text-foreground">{initialMetrics.scheduled_leads}</p>
        </div>
      </section>

      {/* Kanban Board */}
      <section>
        <CrmPipelineBoard
          boardData={initialBoard}
          locale={locale}
          onLeadStageChange={handleStageChange}
        />
      </section>
    </div>
  );
}
