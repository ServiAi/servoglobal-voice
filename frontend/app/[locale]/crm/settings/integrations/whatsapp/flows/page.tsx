import { getTranslations } from 'next-intl/server';
import { WhatsAppFlowsList } from '@/components/crm/integrations/whatsapp-flows/WhatsAppFlowsList';
import { fetchWhatsAppConfig } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchWhatsAppFlows } from '@/lib/api/whatsapp-flows';
import { getIntegrationAccess } from '@/lib/integrations/server';

export const dynamic = 'force-dynamic';

export default async function WhatsAppFlowsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const token = await getIntegrationAccess(locale, 'whatsapp');
  const [flowsResult, configResult, profileResult, t] = await Promise.all([
    fetchWhatsAppFlows(token),
    fetchWhatsAppConfig(token),
    fetchMeProfile(token),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp.flows' }),
  ]);
  const canEdit = profileResult.ok && ['platform_admin', 'tenant_admin'].includes(profileResult.profile.role);
  const configured = configResult.ok && configResult.data.status === 'active' && configResult.data.has_secret && Boolean(configResult.data.business_account_id);
  return <section className="space-y-5" aria-labelledby="whatsapp-flows-title"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600">Flow Studio</p><h2 id="whatsapp-flows-title" className="mt-2 text-2xl font-bold tracking-tight">{t('title')}</h2><p className="mt-1 text-sm text-muted-foreground">{t('description')}</p></div><WhatsAppFlowsList locale={locale} flows={flowsResult.ok ? flowsResult.data : []} canEdit={canEdit} configured={configured} />{!flowsResult.ok ? <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{flowsResult.detail}</p> : null}</section>;
}
