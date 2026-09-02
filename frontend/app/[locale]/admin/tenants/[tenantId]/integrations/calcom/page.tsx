import { getTranslations } from 'next-intl/server';
import { CalComIntegrationCard } from '@/components/crm/integrations/CalComIntegrationCard';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { fetchAdminTenantBookingConfig } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantCalComPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath } = await getAdminIntegrationAccess(locale, tenantId, 'calcom');
  const [result, t] = await Promise.all([fetchAdminTenantBookingConfig(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog' })]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} integrationsPath={integrationsPath} name={t('providers.calcom.name')} description={t('providers.calcom.description')}><CalComIntegrationCard accessToken={accessToken} initialConfig={result.ok ? result.data : undefined} mode="admin" tenantId={tenantId} /></IntegrationDetailShell>;
}
