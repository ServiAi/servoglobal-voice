import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { getTranslations } from 'next-intl/server';
import { IntegrationAvailabilityPanel } from '@/components/crm/integrations/IntegrationAvailabilityPanel';
import { IntegrationCatalog } from '@/components/crm/integrations/IntegrationCatalog';
import { fetchAdminTenantIntegrationAvailability, fetchAdminTenantIntegrationStatuses } from '@/lib/api/crm';
import { redirectAdminAccessFailure } from '@/lib/auth/server';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';
import type { IntegrationProvider } from '@/types/crm';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

const ADMIN_CONFIGURABLE_PROVIDERS: IntegrationProvider[] = [
  'whatsapp',
  'resend',
  'voice',
  'calcom',
  'google_calendar',
];

export default async function AdminTenantIntegrationsPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath, returnTo } = await getAdminIntegrationAccess(locale, tenantId);
  const [availabilityResult, statusesResult, t] = await Promise.all([
    fetchAdminTenantIntegrationAvailability(accessToken, tenantId),
    fetchAdminTenantIntegrationStatuses(accessToken, tenantId),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);

  if (!availabilityResult.ok) redirectAdminAccessFailure(availabilityResult.status, locale, returnTo);

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-7">
      <Link href={`/${locale}/admin/tenants/${tenantId}`} className="inline-flex w-fit items-center gap-2 rounded-sm text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        <ArrowLeft className="size-4" aria-hidden="true" />
        {t('admin.back')}
      </Link>
      <header className="flex flex-col gap-4 border-l-4 border-primary pl-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('admin.eyebrow')}</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-foreground">{t('title')}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">{t('admin.description')}</p>
        </div>
        <span className="w-fit rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground">{t('available', { count: ADMIN_CONFIGURABLE_PROVIDERS.length })}</span>
      </header>
      {availabilityResult.ok ? (
        <IntegrationAvailabilityPanel accessToken={accessToken} tenantId={tenantId} initialItems={availabilityResult.data} />
      ) : (
        <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">{t('admin.availability.loadError')}</div>
      )}
      <IntegrationCatalog locale={locale} enabledProviders={ADMIN_CONFIGURABLE_PROVIDERS} statuses={statusesResult.ok ? statusesResult.data : []} loadError={!statusesResult.ok} basePath={integrationsPath} />
    </div>
  );
}
