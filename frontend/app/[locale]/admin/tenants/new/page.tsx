import { redirect } from 'next/navigation';

import { locales, type Locale } from '@/i18n';
import { getAccessToken } from '@/lib/auth/server';

import { NewTenantClient } from './new-tenant-client';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function NewTenantPage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/admin/tenants/new`);
  }

  return <NewTenantClient locale={locale} />;
}
