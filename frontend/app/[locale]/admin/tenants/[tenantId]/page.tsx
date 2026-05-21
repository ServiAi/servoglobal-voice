import { redirect } from 'next/navigation';

import { locales, type Locale } from '@/i18n';
import { fetchTenantDetail } from '@/lib/api/tenants';
import { getAccessToken } from '@/lib/auth/server';

import { TenantDetailClient } from './tenant-detail-client';

type Props = {
  params: Promise<{ locale: string; tenantId: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function TenantDetailPage({ params }: Props) {
  const { locale: rawLocale, tenantId } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/admin/tenants/${tenantId}`);
  }

  const result = await fetchTenantDetail(accessToken, tenantId);

  if (!result.ok && result.status === 401) {
    redirect(`/api/auth/login?returnTo=/${locale}/admin/tenants/${tenantId}`);
  }

  return (
    <TenantDetailClient
      locale={locale}
      tenantId={tenantId}
      initialTenant={result.ok ? result.data : null}
      initialError={result.ok ? null : result.detail}
    />
  );
}
