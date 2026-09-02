import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { VoiceIntegrationCard } from '@/components/crm/integrations/VoiceIntegrationCard';
import { fetchAdminTenantVoiceAgents, fetchAdminTenantVoiceConfig } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantVoicePage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken, integrationsPath } = await getAdminIntegrationAccess(locale, tenantId, 'voice');
  const [configResult, agentsResult, t] = await Promise.all([fetchAdminTenantVoiceConfig(accessToken, tenantId), fetchAdminTenantVoiceAgents(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog' })]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} integrationsPath={integrationsPath} name={t('providers.voice.name')} description={t('providers.voice.description')}><VoiceIntegrationCard accessToken={accessToken} initialConfig={configResult.ok ? configResult.data : undefined} initialAgents={agentsResult.ok ? agentsResult.data : []} mode="admin" tenantId={tenantId} /></IntegrationDetailShell>;
}
