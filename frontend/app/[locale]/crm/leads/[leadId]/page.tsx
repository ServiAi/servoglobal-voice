import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmLeadDetail } from '@/lib/api/crm';
import { LeadDetailClient } from './lead-detail-client';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

type Props = {
  params: Promise<{ locale: string; leadId: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function LeadDetailPage({ params }: Props) {
  const { locale: rawLocale, leadId } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/leads/${leadId}`);
  }

  const result = await fetchCrmLeadDetail(accessToken, leadId);

  if (!result.ok) {
    // If backend returns 404, we MUST show "Recurso no encontrado" without revealing tenant details.
    if (result.status === 404) {
      return (
        <div className="mx-auto max-w-md rounded-xl border border-border bg-card p-8 text-center shadow-md my-12">
          <h3 className="text-xl font-bold text-foreground">Recurso no encontrado</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            El prospecto o recurso solicitado no existe o no tienes permisos para acceder a él.
          </p>
          <div className="mt-6">
            <Link
              href={`/${locale}/crm/leads`}
              className="inline-flex items-center gap-2 rounded-md bg-violet-600 px-4 py-2 text-xs font-bold text-white hover:bg-violet-500 shadow-sm transition"
            >
              <ArrowLeft className="h-4 w-4" /> Volver al listado
            </Link>
          </div>
        </div>
      );
    }

    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar detalle del lead</h3>
        <p className="mt-2 text-sm">{result.detail}</p>
        <Link
          href={`/${locale}/crm/leads`}
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Volver al listado
        </Link>
      </div>
    );
  }

  return (
    <LeadDetailClient
      lead={result.data}
      accessToken={accessToken}
      locale={locale}
    />
  );
}
