import Link from 'next/link';
import { ArrowRight, FileText, KeyRound, Send } from 'lucide-react';
import { getTranslations } from 'next-intl/server';
import { CrmIntegrationStatusBadge } from '@/components/crm/integrations/CrmIntegrationStatusBadge';
import { fetchWhatsAppConfig, fetchWhatsAppTemplates } from '@/lib/api/crm';
import { resolveIntegrationStatus } from '@/lib/integrations/catalog';
import { getIntegrationAccess } from '@/lib/integrations/server';

type Props = { params: Promise<{ locale: string }> };

export default async function WhatsAppOverviewPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getIntegrationAccess(locale, 'whatsapp');
  const [configResult, templatesResult, t] = await Promise.all([
    fetchWhatsAppConfig(accessToken),
    fetchWhatsAppTemplates(accessToken),
    getTranslations({ locale, namespace: 'crm.integrationsCatalog.whatsapp' }),
  ]);
  const config = configResult.ok ? configResult.data : undefined;
  const accountConfigured = Boolean(config?.phone_number_id || config?.has_secret);
  const status = resolveIntegrationStatus(configResult.ok, config, accountConfigured);
  const base = `/${locale}/crm/settings/integrations/whatsapp`;
  const actions = [
    { href: `${base}/account`, icon: KeyRound, label: t('quickActions.account') },
    { href: `${base}/templates`, icon: FileText, label: t('quickActions.templates') },
    { href: `${base}/test`, icon: Send, label: t('quickActions.test') },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-foreground">{t('overview.title')}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{t('overview.description')}</p>
      </div>
      <section className="grid gap-4 sm:grid-cols-3" aria-label={t('overview.summaryLabel')}>
        <div className="rounded-xl border border-border bg-card p-5 shadow-xs"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{t('overview.status')}</p><div className="mt-3"><CrmIntegrationStatusBadge status={status} /></div></div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-xs"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{t('overview.account')}</p><p className="mt-3 text-lg font-semibold text-foreground">{t(accountConfigured ? 'overview.configured' : 'overview.notConfigured')}</p></div>
        <div className="rounded-xl border border-border bg-card p-5 shadow-xs"><p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{t('overview.templates')}</p><p className="mt-3 text-2xl font-bold tabular-nums text-foreground">{templatesResult.ok ? templatesResult.data.length : '—'}</p></div>
      </section>
      <section aria-labelledby="whatsapp-quick-actions" className="space-y-3">
        <h2 id="whatsapp-quick-actions" className="text-base font-semibold text-foreground">{t('quickActions.title')}</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {actions.map(({ href, icon: Icon, label }) => <Link key={href} href={href} className="group flex min-h-20 items-center gap-3 rounded-xl border border-border bg-card p-4 text-sm font-semibold text-foreground outline-none transition hover:border-primary/30 hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring"><Icon className="size-5 text-primary" aria-hidden="true" /><span className="flex-1">{label}</span><ArrowRight className="size-4 transition-transform group-hover:translate-x-1" aria-hidden="true" /></Link>)}
        </div>
      </section>
    </div>
  );
}
