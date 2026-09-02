import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { ResendIntegrationCard } from '@/components/crm/integrations/ResendIntegrationCard';
import { fetchAdminTenantIntegrations } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantResendPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath } = await getAdminIntegrationAccess(locale, tenantId, 'resend');
  const [result, t] = await Promise.all([fetchAdminTenantIntegrations(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog' })]);
  const config = result.ok ? result.data.find((item) => item.provider === 'resend') : undefined;
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} integrationsPath={integrationsPath} name={t('providers.resend.name')} description={t('providers.resend.description')}><ResendIntegrationCard accessToken={accessToken} initialConfig={config} mode="admin" tenantId={tenantId} /></IntegrationDetailShell>;
}
