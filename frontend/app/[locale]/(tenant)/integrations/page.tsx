import { getTranslations } from 'next-intl/server';
import { redirect } from 'next/navigation';
import { IntegrationCatalog } from '@/components/crm/integrations/IntegrationCatalog';
import { fetchIntegrationAvailability, fetchIntegrationCatalogStatuses } from '@/lib/api/crm';
import { getAccessToken } from '@/lib/auth/server';

type Props = { params: Promise<{ locale: string }> };

export const dynamic = 'force-dynamic';

export default async function CrmIntegrationsPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/integrations`);

  const [availabilityResult, statusesResult] = await Promise.all([
    fetchIntegrationAvailability(accessToken),
    fetchIntegrationCatalogStatuses(accessToken),
  ]);
  const enabledProviders = availabilityResult.ok
    ? availabilityResult.data.filter((item) => item.enabled).map((item) => item.provider)
    : statusesResult.ok
      ? statusesResult.data.map((item) => item.provider)
      : [];
  const t = await getTranslations({ locale, namespace: 'crm.integrationsCatalog' });

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-7">
      <header className="flex flex-col gap-4 border-l-4 border-primary pl-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{t('eyebrow')}</p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">{t('title')}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('description')}</p>
        </div>
        <p className="text-sm text-muted-foreground">{t('available', { count: enabledProviders.length })}</p>
      </header>

      <IntegrationCatalog
        locale={locale}
        enabledProviders={enabledProviders}
        statuses={statusesResult.ok ? statusesResult.data : []}
        loadError={!availabilityResult.ok || !statusesResult.ok}
      />
    </div>
  );
}
