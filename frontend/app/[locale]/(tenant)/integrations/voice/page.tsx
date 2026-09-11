import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { UltravoxAdminWorkspace } from '@/components/crm/integrations/UltravoxAdminWorkspace';
import { fetchVoiceAgents, fetchVoiceConfig } from '@/lib/api/crm';
import { fetchUltravoxAgents, fetchUltravoxVoices } from '@/lib/api/ultravox-admin';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function VoiceIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'voice');
  const [configResult, agentsResult, providerAgentsResult, voicesResult, t] = await Promise.all([
    fetchVoiceConfig(accessToken),
    fetchVoiceAgents(accessToken),
    fetchUltravoxAgents(accessToken, { pageSize: 50 }),
    fetchUltravoxVoices(accessToken, { pageSize: 50 }),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.voice.name')} description={t('providers.voice.description')}><UltravoxAdminWorkspace accessToken={accessToken} locale={locale} initialConfig={configResult.ok ? configResult.data : undefined} initialVoiceAgents={agentsResult.ok ? agentsResult.data : []} initialAgents={providerAgentsResult.ok ? providerAgentsResult.data : undefined} initialVoices={voicesResult.ok ? voicesResult.data : undefined} /></IntegrationDetailShell>;
}
