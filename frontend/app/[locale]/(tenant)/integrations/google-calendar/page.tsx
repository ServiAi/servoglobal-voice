import { getTranslations } from 'next-intl/server';
import { GoogleCalendarIntegrationCard } from '@/components/crm/integrations/GoogleCalendarIntegrationCard';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { fetchGoogleCalendarConnections } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };
export const dynamic = 'force-dynamic';

export default async function GoogleCalendarIntegrationPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'google_calendar');
  const [result, t] = await Promise.all([
    fetchGoogleCalendarConnections(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog' }),
  ]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} name={t('providers.google_calendar.name')} description={t('providers.google_calendar.description')}><GoogleCalendarIntegrationCard accessToken={accessToken} locale={locale} connections={result.ok ? result.data : []} /></IntegrationDetailShell>;
}
