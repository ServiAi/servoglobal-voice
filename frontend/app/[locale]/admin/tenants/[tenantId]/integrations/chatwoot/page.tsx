import { getTranslations } from 'next-intl/server';
import { ChatwootIntegrationCard } from '@/components/crm/integrations/ChatwootIntegrationCard';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { fetchAdminTenantChatwootConfig } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantChatwootPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath } = await getAdminIntegrationAccess(locale, tenantId, 'chatwoot');
  const [result, t] = await Promise.all([
    fetchAdminTenantChatwootConfig(accessToken, tenantId),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return (
    <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} integrationsPath={integrationsPath} name={t('providers.chatwoot.name')} description={t('providers.chatwoot.description')}>
      <ChatwootIntegrationCard accessToken={accessToken} initialConfig={result.ok ? result.data : undefined} mode="admin" tenantId={tenantId} />
    </IntegrationDetailShell>
  );
}
