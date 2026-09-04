import { getTranslations } from 'next-intl/server';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { ResendIntegrationCard } from '@/components/crm/integrations/ResendIntegrationCard';
import { fetchTenantIntegrations } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function ResendIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'resend');
  const [result, t] = await Promise.all([
    fetchTenantIntegrations(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  const config = result.ok ? result.data.find((item) => item.provider === 'resend') : undefined;
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.resend.name')} description={t('providers.resend.description')}><ResendIntegrationCard accessToken={accessToken} initialConfig={config} /></IntegrationDetailShell>;
}
