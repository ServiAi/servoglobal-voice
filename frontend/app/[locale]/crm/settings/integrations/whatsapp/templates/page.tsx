import { getTranslations } from 'next-intl/server';
import { WhatsAppSection } from '@/components/crm/integrations/WhatsAppSection';
import { fetchWhatsAppConfig, fetchWhatsAppTemplates } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };

export default async function WhatsAppTemplatesPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'whatsapp');
  const [configResult, templatesResult, t] = await Promise.all([fetchWhatsAppConfig(accessToken), fetchWhatsAppTemplates(accessToken), getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.templates' })]);
  return <section className="space-y-4" aria-labelledby="whatsapp-templates-title"><div><h2 id="whatsapp-templates-title" className="text-xl font-semibold text-foreground">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppSection accessToken={accessToken} section="templates" initialConfig={configResult.ok ? configResult.data : undefined} templates={templatesResult.ok ? templatesResult.data : []} /></section>;
}
