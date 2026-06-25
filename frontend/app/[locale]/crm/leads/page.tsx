import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmLeads } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import { CrmLeadFilters } from '@/components/crm/CrmLeadFilters';
import { CrmLeadsTable } from '@/components/crm/CrmLeadsTable';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

function parseBoolean(value: string | string[] | undefined): boolean | undefined {
  if (value === 'true') return true;
  if (value === 'false') return false;
  return undefined;
}

function parsePositiveInteger(value: string | string[] | undefined, fallback: number): number {
  if (typeof value !== 'string') return fallback;
  const parsed = parseInt(value, 10);
  return isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export default async function CrmLeadsPage({ params, searchParams }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/leads`);
  }

  const resolvedSearchParams = await searchParams;

  // Build filters from query string
  const filters = {
    page: parsePositiveInteger(resolvedSearchParams.page, 1),
    page_size: parsePositiveInteger(resolvedSearchParams.page_size, 20),
    stage_key: typeof resolvedSearchParams.stage_key === 'string' ? resolvedSearchParams.stage_key : undefined,
    status: typeof resolvedSearchParams.status === 'string' ? resolvedSearchParams.status : undefined,
    search: typeof resolvedSearchParams.search === 'string' ? resolvedSearchParams.search : undefined,
    source: typeof resolvedSearchParams.source === 'string' ? resolvedSearchParams.source : undefined,
    campaign: typeof resolvedSearchParams.campaign === 'string' ? resolvedSearchParams.campaign : undefined,
    has_phone: parseBoolean(resolvedSearchParams.has_phone),
    has_email: parseBoolean(resolvedSearchParams.has_email),
    sort_by: typeof resolvedSearchParams.sort_by === 'string' ? resolvedSearchParams.sort_by : 'updated_at',
    sort_order: typeof resolvedSearchParams.sort_order === 'string' ? resolvedSearchParams.sort_order : 'desc',
    date_from: typeof resolvedSearchParams.date_from === 'string' ? resolvedSearchParams.date_from : undefined,
    date_to: typeof resolvedSearchParams.date_to === 'string' ? resolvedSearchParams.date_to : undefined,
  };

  const result = await fetchCrmLeads(accessToken, filters);
  const meResult = await fetchMeProfile(accessToken);
  const userRole = meResult.ok ? meResult.profile.role : undefined;

  if (!result.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar listado de leads</h3>
        <p className="mt-2 text-sm">{result.detail}</p>
        <Link
          href={`/${locale}/crm`}
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Volver al Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header path */}
      <div className="flex items-center gap-4">
        <Link
          href={`/${locale}/crm`}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card text-muted-foreground hover:text-foreground transition shadow-2xs"
          title="Volver"
        >
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">
            Listado de Leads
          </h2>
          <p className="text-sm text-muted-foreground">
            Busca, filtra y examina a todos tus prospectos calificados o en proceso.
          </p>
        </div>
      </div>

      {/* Filters form */}
      <CrmLeadFilters />

      {/* Leads Table */}
      <CrmLeadsTable data={result.data} locale={locale} accessToken={accessToken} userRole={userRole} />
    </div>
  );
}
