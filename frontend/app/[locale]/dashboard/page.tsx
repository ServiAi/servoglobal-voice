import { redirect } from 'next/navigation';

import { fetchMeProfile } from '@/lib/api/me';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import {
  fetchKpis,
  fetchTrends,
  fetchStatusDistribution,
  fetchAgentDistribution,
  fetchHeatmap,
  fetchRecentCalls,
  type DashboardFilters
} from '@/lib/api/dashboard';

import { Suspense } from 'react';
import { DashboardFilters as DashboardFiltersUI } from '@/components/dashboard/DashboardFilters';
import { KpiCards } from '@/components/dashboard/KpiCards';
import { TrendsChart } from '@/components/dashboard/TrendsChart';
import { StatusDistributionChart } from '@/components/dashboard/StatusDistributionChart';
import { AgentDistributionChart } from '@/components/dashboard/AgentDistributionChart';
import { HeatmapChart } from '@/components/dashboard/HeatmapChart';
import { RecentCallsTable } from '@/components/dashboard/RecentCallsTable';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function PrivateDashboardBase({ params, searchParams }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/dashboard`);
  }

  const result = await fetchMeProfile(accessToken);

  if (!result.ok && result.status === 401) {
    redirect(`/api/auth/login?returnTo=/${locale}/dashboard`);
  }

  if (!result.ok) {
    redirect(`/${locale}/dashboard/no-access`);
  }

  const { profile } = result;

  // Await searchParams and build filters
  const resolvedSearchParams = await searchParams;
  const filters: DashboardFilters = {
    from: typeof resolvedSearchParams.from === 'string' ? resolvedSearchParams.from : undefined,
    to: typeof resolvedSearchParams.to === 'string' ? resolvedSearchParams.to : undefined,
    agent_id: typeof resolvedSearchParams.agent_id === 'string' ? resolvedSearchParams.agent_id : undefined,
    status: typeof resolvedSearchParams.status === 'string' ? resolvedSearchParams.status : undefined,
  };

  // Fetch all dashboard data concurrently
  const [
    kpisRes,
    trendsRes,
    statusRes,
    agentRes,
    heatmapRes,
    recentRes
  ] = await Promise.all([
    fetchKpis(accessToken, filters),
    fetchTrends(accessToken, filters),
    fetchStatusDistribution(accessToken, filters),
    fetchAgentDistribution(accessToken, filters),
    fetchHeatmap(accessToken, filters),
    fetchRecentCalls(accessToken, filters)
  ]);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
        <header className="flex flex-col gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase text-cyan-300">
              ServiGlobal IA
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal">
              Dashboard de Métricas
            </h1>
            <p className="mt-1 text-sm text-zinc-400">
              {profile.tenant_name} • {profile.name ?? profile.email}
            </p>
          </div>
          <form action="/api/auth/logout" method="get">
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-md border border-white/15 bg-zinc-900 px-4 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800 hover:text-cyan-200"
            >
              Cerrar sesión
            </button>
          </form>
        </header>

        {/* Filters */}
        <Suspense fallback={<div className="h-20 animate-pulse rounded-xl border border-white/10 bg-zinc-900/50 mb-8" />}>
          <DashboardFiltersUI />
        </Suspense>

        {/* Dashboard Content */}
        {kpisRes.ok ? (
          <KpiCards data={kpisRes.data} />
        ) : (
          <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400 mb-8">
            Error cargando KPIs: {kpisRes.detail}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 mb-6">
          <div className="lg:col-span-2">
            {trendsRes.ok ? (
              <TrendsChart data={trendsRes.data} />
            ) : (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
                Error cargando tendencias.
              </div>
            )}
          </div>
          <div className="lg:col-span-1">
            {statusRes.ok ? (
              <StatusDistributionChart data={statusRes.data} />
            ) : (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
                Error cargando estados.
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
          <div>
            {agentRes.ok ? (
              <AgentDistributionChart data={agentRes.data} />
            ) : (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
                Error cargando agentes.
              </div>
            )}
          </div>
          <div>
            {heatmapRes.ok ? (
              <HeatmapChart data={heatmapRes.data} />
            ) : (
              <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
                Error cargando mapa de calor.
              </div>
            )}
          </div>
        </div>

        <div className="mt-4">
          {recentRes.ok ? (
            <RecentCallsTable data={recentRes.data} />
          ) : (
            <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
              Error cargando llamadas recientes.
            </div>
          )}
        </div>

      </section>
    </main>
  );
}
