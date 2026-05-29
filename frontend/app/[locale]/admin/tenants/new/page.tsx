import { locales, type Locale } from '@/i18n';
import { requireInternalAdminAccess } from '@/lib/auth/server';

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
  await requireInternalAdminAccess(locale, `/${locale}/admin/tenants/new`);

  return <NewTenantClient locale={locale} />;
}
