import { getTranslations } from 'next-intl/server';
import { WhatsAppSection } from '@/components/crm/integrations/WhatsAppSection';
import { fetchAdminTenantWhatsAppConfig, fetchAdminTenantWhatsAppTemplates } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantWhatsAppTestPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken } = await getAdminIntegrationAccess(locale, tenantId, 'whatsapp/test');
  const [configResult, templatesResult, t] = await Promise.all([fetchAdminTenantWhatsAppConfig(accessToken, tenantId), fetchAdminTenantWhatsAppTemplates(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.test' })]);
  return <section className="space-y-4" aria-labelledby="admin-whatsapp-test-title"><div><h2 id="admin-whatsapp-test-title" className="text-xl font-semibold text-foreground">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppSection accessToken={accessToken} section="test" initialConfig={configResult.ok ? configResult.data : undefined} templates={templatesResult.ok ? templatesResult.data : []} mode="admin" tenantId={tenantId} /></section>;
}
