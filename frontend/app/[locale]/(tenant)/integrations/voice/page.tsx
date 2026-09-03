import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { VoiceIntegrationCard } from '@/components/crm/integrations/VoiceIntegrationCard';
import { fetchVoiceAgents, fetchVoiceConfig } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function VoiceIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'voice');
  const [configResult, agentsResult, t] = await Promise.all([
    fetchVoiceConfig(accessToken),
    fetchVoiceAgents(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.voice.name')} description={t('providers.voice.description')}><VoiceIntegrationCard accessToken={accessToken} initialConfig={configResult.ok ? configResult.data : undefined} initialAgents={agentsResult.ok ? agentsResult.data : []} /></IntegrationDetailShell>;
}
