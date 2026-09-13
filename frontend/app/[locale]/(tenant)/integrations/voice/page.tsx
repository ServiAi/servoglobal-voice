import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { VoiceProviderAdminWorkspace } from '@/components/crm/integrations/VoiceProviderAdminWorkspace';
import { fetchVoiceAgents, fetchVoiceConfig } from '@/lib/api/crm';
import { fetchProviderAgents, fetchProviderVoices } from '@/lib/api/voice-provider-admin';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

// Ultravox is the only voice provider with a real backend adapter today
// (see backend/app/services/voice_provider_admin.py); a future provider is
// added here without rebuilding VoiceProviderAdminWorkspace.
const PROVIDER = { key: 'ultravox', name: 'Ultravox' };

export default async function VoiceIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'voice');
  const [configResult, agentsResult, providerAgentsResult, voicesResult, t] = await Promise.all([
    fetchVoiceConfig(accessToken),
    fetchVoiceAgents(accessToken),
    fetchProviderAgents(accessToken, PROVIDER.key, { pageSize: 50 }),
    fetchProviderVoices(accessToken, PROVIDER.key, { pageSize: 50 }),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.voice.name')} description={t('providers.voice.description')}><VoiceProviderAdminWorkspace accessToken={accessToken} locale={locale} provider={PROVIDER} initialConfig={configResult.ok ? configResult.data : undefined} initialVoiceAgents={agentsResult.ok ? agentsResult.data : []} initialAgents={providerAgentsResult.ok ? providerAgentsResult.data : undefined} initialVoices={voicesResult.ok ? voicesResult.data : undefined} /></IntegrationDetailShell>;
}
