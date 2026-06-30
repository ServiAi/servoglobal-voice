import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { locales, type Locale } from '@/i18n';
import { fetchAdminTenantForms } from '@/lib/api/crm';
import {
  redirectAdminAccessFailure,
  requireInternalAdminAccess,
} from '@/lib/auth/server';
import { FormsSettingsClient } from '@/components/crm/forms/FormsSettingsClient';

type Props = {
  params: Promise<{ locale: string; tenantId: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function AdminTenantFormsPage({ params }: Props) {
  const { locale: rawLocale, tenantId } = await params;
  const locale = normalizeLocale(rawLocale);
  const returnTo = `/${locale}/admin/tenants/${tenantId}/forms`;
  const { accessToken } = await requireInternalAdminAccess(locale, returnTo);
  const formsResult = await fetchAdminTenantForms(accessToken, tenantId);
  if (!formsResult.ok) {
    redirectAdminAccessFailure(formsResult.status, locale, returnTo);
    return null;
  }
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <Link href={`/${locale}/admin/tenants/${tenantId}`} className="inline-flex items-center gap-1.5 text-sm text-zinc-500 transition hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200">
        <ArrowLeft className="h-4 w-4" />
        Volver al detalle del tenant
      </Link>
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Formularios del tenant</h1>
        <p className="text-sm text-muted-foreground">Links publicos seguros por lead</p>
      </div>
      <FormsSettingsClient accessToken={accessToken} initialForms={formsResult.data} mode="admin" tenantId={tenantId} />
    </div>
  );
}
