import { Suspense } from 'react';
import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { fetchRecentCalls, type DashboardFilters } from '@/lib/api/dashboard';
import { DashboardFilters as DashboardFiltersUI } from '@/components/dashboard/DashboardFilters';
import { RecentCallsTable } from '@/components/dashboard/RecentCallsTable';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizePositiveInteger(value: string | string[] | undefined, fallback: number) {
  if (typeof value !== 'string') return fallback;
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export default async function VoiceAiCallsPage({ params, searchParams }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/calls`);
  }

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
    page: normalizePositiveInteger(resolvedSearchParams.page, 1),
    page_size: normalizePositiveInteger(resolvedSearchParams.page_size, 10),
  };

  const recentRes = await fetchRecentCalls(accessToken, filters);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="border-b border-border pb-5">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Llamadas</h1>
        <p className="mt-1 text-sm text-muted-foreground">Historial de llamadas atendidas por tus agentes de voz.</p>
      </header>

      <Suspense fallback={<div className="h-20 animate-pulse rounded-xl border border-border bg-muted/50" />}>
        <DashboardFiltersUI initialFilters={filters} initialQueryString={initialQueryParams.toString()} />
      </Suspense>

      {recentRes.ok ? (
        <RecentCallsTable data={recentRes.data} />
      ) : (
        <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-4 text-destructive">
          Error cargando llamadas recientes: {recentRes.detail}
        </div>
      )}
    </div>
  );
}
