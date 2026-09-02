import { getTranslations } from 'next-intl/server';
import { WhatsAppSection } from '@/components/crm/integrations/WhatsAppSection';
import { fetchAdminTenantWhatsAppConfig } from '@/lib/api/crm';
import { getAdminIntegrationAccess } from '@/lib/integrations/admin-server';

type Props = { params: Promise<{ locale: string; tenantId: string }> };

export default async function AdminTenantWhatsAppAccountPage({ params }: Props) {
  const { locale, tenantId } = await params;
  const { accessToken } = await getAdminIntegrationAccess(locale, tenantId, 'whatsapp/account');
  const [result, t] = await Promise.all([fetchAdminTenantWhatsAppConfig(accessToken, tenantId), getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.account' })]);
  return <section className="space-y-4" aria-labelledby="admin-whatsapp-account-title"><div><h2 id="admin-whatsapp-account-title" className="text-xl font-semibold text-foreground">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppSection accessToken={accessToken} section="account" initialConfig={result.ok ? result.data : undefined} mode="admin" tenantId={tenantId} /></section>;
}
