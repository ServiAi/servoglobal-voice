import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmDashboard } from '@/lib/api/crm';
import { CrmDashboardViewClient } from './crm-dashboard-view-client';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function CrmAnalyticsPage({ params, searchParams }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/analytics`);
  }

  const resolvedSearchParams = await searchParams;

  const range = typeof resolvedSearchParams.range === 'string' ? resolvedSearchParams.range : undefined;
  const date_from = typeof resolvedSearchParams.date_from === 'string' ? resolvedSearchParams.date_from : undefined;
  const date_to = typeof resolvedSearchParams.date_to === 'string' ? resolvedSearchParams.date_to : undefined;
  const source = typeof resolvedSearchParams.source === 'string' ? resolvedSearchParams.source : undefined;
  const campaign = typeof resolvedSearchParams.campaign === 'string' ? resolvedSearchParams.campaign : undefined;

  const dashboardRes = await fetchCrmDashboard(accessToken, {
    range,
    date_from,
    date_to,
    source,
    campaign,
  });

  if (!dashboardRes.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar el rendimiento CRM</h3>
        <p className="mt-2 text-sm">{dashboardRes.detail}</p>
      </div>
    );
  }

  return <CrmDashboardViewClient initialData={dashboardRes.data} locale={locale} />;
}
