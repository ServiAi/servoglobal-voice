import { getTranslations } from 'next-intl/server';
import { WhatsAppSection } from '@/components/crm/integrations/WhatsAppSection';
import { fetchAdminTenantWhatsAppConfig, fetchAdminTenantWhatsAppTemplates } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantWhatsAppTemplatesPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken } = await getAdminIntegrationAccess(locale, tenantId, 'whatsapp/templates');
  const [configResult, templatesResult, t] = await Promise.all([fetchAdminTenantWhatsAppConfig(accessToken, tenantId), fetchAdminTenantWhatsAppTemplates(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.templates' })]);
  return <section className="space-y-4" aria-labelledby="admin-whatsapp-templates-title"><div><h2 id="admin-whatsapp-templates-title" className="text-xl font-semibold text-foreground">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppSection accessToken={accessToken} section="templates" initialConfig={configResult.ok ? configResult.data : undefined} templates={templatesResult.ok ? templatesResult.data : []} mode="admin" tenantId={tenantId} /></section>;
}
