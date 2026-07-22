import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmDashboard, fetchCrmMetrics, fetchCrmPipelineBoard } from '@/lib/api/crm';
import { CrmDashboardClient } from './crm-dashboard-client';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function CrmDashboardPage({ params, searchParams }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm`);
  }

  const resolvedSearchParams = await searchParams;
  
  // Parse limit per stage from search params
  const limitPerStageStr = typeof resolvedSearchParams.limit_per_stage === 'string' 
    ? resolvedSearchParams.limit_per_stage 
    : undefined;
  const limit_per_stage = limitPerStageStr ? parseInt(limitPerStageStr, 10) : 20;

  // Concurrently fetch board and metrics
  const [metricsRes, boardRes, dashboardRes] = await Promise.all([
    fetchCrmMetrics(accessToken),
    fetchCrmPipelineBoard(accessToken, {
      limit_per_stage,
      search: typeof resolvedSearchParams.search === 'string' ? resolvedSearchParams.search : undefined,
      status: typeof resolvedSearchParams.status === 'string' ? resolvedSearchParams.status : undefined,
    }),
    fetchCrmDashboard(accessToken, { range: '30d' }),
  ]);

  if (!metricsRes.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar métricas CRM</h3>
        <p className="mt-2 text-sm">{metricsRes.detail}</p>
      </div>
    );
  }

  if (!boardRes.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar el embudo de ventas (Pipeline)</h3>
        <p className="mt-2 text-sm">{boardRes.detail}</p>
      </div>
    );
  }

  if (!dashboardRes.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar el resumen operativo CRM</h3>
        <p className="mt-2 text-sm">{dashboardRes.detail}</p>
      </div>
    );
  }

  return (
    <CrmDashboardClient
      initialMetrics={metricsRes.data}
      initialBoard={boardRes.data}
      initialDashboard={dashboardRes.data}
      accessToken={accessToken}
      locale={locale}
    />
  );
}
