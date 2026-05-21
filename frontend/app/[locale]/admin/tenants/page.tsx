import { redirect } from 'next/navigation';

import { locales, type Locale } from '@/i18n';
import { fetchTenantsList } from '@/lib/api/tenants';
import { getAccessToken } from '@/lib/auth/server';

import { TenantsListClient } from './tenants-list-client';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function TenantsListPage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/admin/tenants`);
  }

  const result = await fetchTenantsList(accessToken);

  if (!result.ok && result.status === 401) {
    redirect(`/api/auth/login?returnTo=/${locale}/admin/tenants`);
  }

  return (
    <TenantsListClient
      locale={locale}
      initialTenants={result.ok ? result.data : []}
      initialError={result.ok ? null : result.detail}
    />
  );
}
