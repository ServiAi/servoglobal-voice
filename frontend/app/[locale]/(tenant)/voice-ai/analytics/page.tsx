import { Suspense } from 'react';
import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { getAccessToken } from '@/lib/auth/server';
import {
  fetchAgentDistribution,
  fetchHeatmap,
  fetchKpis,
  fetchStatusDistribution,
  fetchTrends,
  fetchUsage,
  fetchSavingsComparison,
  type DashboardFilters,
} from '@/lib/api/dashboard';
import { fetchCrmDashboard } from '@/lib/api/crm';
import { DashboardFilters as DashboardFiltersUI } from '@/components/dashboard/DashboardFilters';
import { KpiCards } from '@/components/dashboard/KpiCards';
import { TrendsChart } from '@/components/dashboard/TrendsChart';
import { StatusDistributionChart } from '@/components/dashboard/StatusDistributionChart';
import { AgentDistributionChart } from '@/components/dashboard/AgentDistributionChart';
import { HeatmapChart } from '@/components/dashboard/HeatmapChart';
import { CallsPanel } from '@/components/voice-ai/CallsPanel';
import { TenantSavingsComparison } from '@/components/tenant-usage/TenantSavingsComparison';
import { TenantUsageAlerts } from '@/components/tenant-usage/TenantUsageAlerts';
import { TenantUsageCard } from '@/components/tenant-usage/TenantUsageCard';
import { isUsageLimitStatus } from '@/lib/tenant-plans';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

export default async function VoiceAiAnalyticsPage({ params, searchParams }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/analytics`);
  }

  const t = await getTranslations({ locale, namespace: 'crm.voiceAi' });
  const resolvedSearchParams = await searchParams;
  const initialQueryParams = new URLSearchParams();
  Object.entries(resolvedSearchParams).forEach(([key, value]) => {
    if (typeof value === 'string') initialQueryParams.set(key, value);
  });
  const filters: DashboardFilters = {
    from: typeof resolvedSearchParams.from === 'string' ? resolvedSearchParams.from : undefined,
    to: typeof resolvedSearchParams.to === 'string' ? resolvedSearchParams.to : undefined,
    agent_id: typeof resolvedSearchParams.agent_id === 'string' ? resolvedSearchParams.agent_id : undefined,
    status: typeof resolvedSearchParams.status === 'string' ? resolvedSearchParams.status : undefined,
  };

  const [kpisRes, trendsRes, statusRes, agentRes, heatmapRes, usageRes, savingsRes, crmDashboardRes] = await Promise.all([
    fetchKpis(accessToken, filters),
    fetchTrends(accessToken, filters),
    fetchStatusDistribution(accessToken, filters),
    fetchAgentDistribution(accessToken, filters),
    fetchHeatmap(accessToken, filters),
    fetchUsage(accessToken),
    fetchSavingsComparison(accessToken),
    fetchCrmDashboard(accessToken),
  ]);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="border-b border-border pb-5">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t('analyticsTitle')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('analyticsSubtitle')}</p>
      </header>

      <Suspense fallback={<div className="h-20 animate-pulse rounded-xl border border-border bg-muted/50" />}>
        <DashboardFiltersUI initialFilters={filters} initialQueryString={initialQueryParams.toString()} />
      </Suspense>

      {kpisRes.ok ? (
        <KpiCards data={kpisRes.data} />
      ) : (
        <DashboardError message={t('kpisError', { detail: kpisRes.detail })} />
      )}

      {usageRes.ok && isUsageLimitStatus(usageRes.data.usage_status) && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-red-300">
          {t('usageLimitBanner')}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {usageRes.ok ? <TenantUsageCard usage={usageRes.data} /> : <DashboardError message={t('usageError')} />}
        {usageRes.ok ? <TenantUsageAlerts alerts={usageRes.data.alerts} /> : <DashboardError message={t('alertsError')} />}
      </div>

      {savingsRes.ok ? (
        <TenantSavingsComparison comparison={savingsRes.data} />
      ) : (
        <DashboardError message={t('savingsError')} />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {trendsRes.ok ? <TrendsChart data={trendsRes.data} /> : <DashboardError message={t('trendsError')} />}
        </div>
        <div>
          {statusRes.ok ? <StatusDistributionChart data={statusRes.data} /> : <DashboardError message={t('statusError')} />}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {agentRes.ok ? <AgentDistributionChart data={agentRes.data} /> : <DashboardError message={t('agentsError')} />}
        {heatmapRes.ok ? <HeatmapChart data={heatmapRes.data} /> : <DashboardError message={t('heatmapError')} />}
      </div>

      {crmDashboardRes.ok ? (
        <CallsPanel data={crmDashboardRes.data} locale={locale} />
      ) : (
        <DashboardError message={t('callsError')} />
      )}
    </div>
  );
}

function DashboardError({ message }: { message: string }) {
  return <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-4 text-destructive">{message}</div>;
}
