import { getTranslations } from 'next-intl/server';
import { CalComIntegrationCard } from '@/components/crm/integrations/CalComIntegrationCard';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { fetchBookingConfig } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function CalComIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'calcom');
  const [result, t] = await Promise.all([
    fetchBookingConfig(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.calcom.name')} description={t('providers.calcom.description')}><CalComIntegrationCard accessToken={accessToken} initialConfig={result.ok ? result.data : undefined} /></IntegrationDetailShell>;
}
