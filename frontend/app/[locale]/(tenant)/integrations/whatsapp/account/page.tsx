import { getTranslations } from 'next-intl/server';
import { WhatsAppSection } from '@/components/crm/integrations/WhatsAppSection';
import { fetchWhatsAppConfig } from '@/lib/api/crm';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };

export default async function WhatsAppAccountPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'whatsapp');
  const [result, t] = await Promise.all([fetchWhatsAppConfig(accessToken), getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.account' })]);
  return <section className="space-y-4" aria-labelledby="whatsapp-account-title"><div><h2 id="whatsapp-account-title" className="text-xl font-semibold text-foreground">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppSection accessToken={accessToken} section="account" initialConfig={result.ok ? result.data : undefined} /></section>;
}
