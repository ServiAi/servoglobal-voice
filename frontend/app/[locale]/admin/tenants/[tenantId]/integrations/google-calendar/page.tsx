import { getTranslations } from 'next-intl/server';
import { GoogleCalendarIntegrationCard } from '@/components/crm/integrations/GoogleCalendarIntegrationCard';
import { IntegrationDetailShell } from '@/components/crm/integrations/IntegrationDetailShell';
import { fetchAdminTenantGoogleCalendarConnections } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantGoogleCalendarPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { integrationsPath, accessToken } = await getAdminIntegrationAccess(locale, tenantId, 'google-calendar');
  const [result, t] = await Promise.all([fetchAdminTenantGoogleCalendarConnections(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog' })]);
  return <IntegrationDetailShell locale={locale} integrationsLabel={t('title')} integrationsPath={integrationsPath} name={t('providers.google_calendar.name')} description={t('providers.google_calendar.description')}><GoogleCalendarIntegrationCard locale={locale} connections={result.ok ? result.data : []} /></IntegrationDetailShell>;
}
