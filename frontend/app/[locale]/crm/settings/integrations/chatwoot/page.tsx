import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { ChatwootIntegrationCard } from '@/components/crm/integrations/ChatwootIntegrationCard';
import { fetchChatwootConfig } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function ChatwootIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'chatwoot');
  const [result, t] = await Promise.all([
    fetchChatwootConfig(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  const config = result.ok ? result.data : undefined;
  return (
    <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.chatwoot.name')} description={t('providers.chatwoot.description')}>
      <ChatwootIntegrationCard accessToken={accessToken} initialConfig={config} />
    </IntegrationDetailShell>
  );
}
