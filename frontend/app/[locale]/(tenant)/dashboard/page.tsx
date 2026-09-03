import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { AlertTriangle, ArrowRight, CheckCircle2 } from 'lucide-react';
import { getAccessToken } from '@/lib/auth/server';
import { fetchCrmDashboard, fetchIntegrationCatalogStatuses } from '@/lib/api/crm';
import { fetchKpis, fetchUsage } from '@/lib/api/dashboard';
import { getVoiceCapacityStatus } from '@/lib/permissions/voice-capacity';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

type AttentionItem = { key: string; label: string };

export default async function TenantHomePage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/dashboard`);
  }

  const t = await getTranslations({ locale, namespace: 'crm.tenantHome' });

  const [crmRes, kpisRes, usageRes, integrationsRes] = await Promise.all([
    fetchCrmDashboard(accessToken),
    fetchKpis(accessToken),
    fetchUsage(accessToken),
    fetchIntegrationCatalogStatuses(accessToken),
  ]);

  const attentionItems: AttentionItem[] = [];

  if (crmRes.ok && crmRes.data.kpis.overdue_tasks > 0) {
    attentionItems.push({
      key: 'overdue-tasks',
      label: t('attentionOverdueTasks', { count: crmRes.data.kpis.overdue_tasks }),
    });
  }

  if (usageRes.ok && usageRes.data.usage_percent >= 80) {
    attentionItems.push({
      key: 'usage',
      label: t('attentionUsage', { percent: Math.round(usageRes.data.usage_percent) }),
    });
  }

  if (crmRes.ok) {
    const capacityStatus = getVoiceCapacityStatus(crmRes.data.voice_capacity);
    if (capacityStatus === 'saturated') {
      attentionItems.push({ key: 'capacity', label: t('attentionCapacitySaturated') });
    } else if (capacityStatus === 'high') {
      attentionItems.push({ key: 'capacity', label: t('attentionCapacityHigh') });
    }
  }

  if (integrationsRes.ok) {
    const errored = integrationsRes.data.filter((item) => item.status === 'error');
    if (errored.length > 0) {
      attentionItems.push({
        key: 'integrations',
        label: t('attentionIntegrationErrors', { count: errored.length }),
      });
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="border-b border-border pb-5">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t('title')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('subtitle')}</p>
      </header>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SummaryCard title={t('crmTitle')} href={`/${locale}/crm/analytics`} cta={t('crmCta')}>
          {crmRes.ok ? (
            <MetricGrid
              items={[
                { label: t('crmMetrics.newLeads'), value: crmRes.data.kpis.new_leads },
                { label: t('crmMetrics.qualifiedLeads'), value: crmRes.data.kpis.qualified_leads },
                { label: t('crmMetrics.scheduledLeads'), value: crmRes.data.kpis.scheduled_leads },
                { label: t('crmMetrics.conversion'), value: `${crmRes.data.conversion.win_rate.toFixed(0)}%` },
              ]}
            />
          ) : (
            <ErrorNote message={t('crmError')} />
          )}
        </SummaryCard>

        <SummaryCard title={t('voiceTitle')} href={`/${locale}/voice-ai/analytics`} cta={t('voiceCta')}>
          {kpisRes.ok ? (
            <MetricGrid
              items={[
                { label: t('voiceMetrics.calls'), value: kpisRes.data.calls_total },
                { label: t('voiceMetrics.answered'), value: kpisRes.data.calls_answered },
                { label: t('voiceMetrics.answerRate'), value: `${kpisRes.data.answer_rate.toFixed(0)}%` },
                { label: t('voiceMetrics.minutesUsed'), value: Math.round(kpisRes.data.billed_minutes) },
              ]}
            />
          ) : (
            <ErrorNote message={t('voiceError')} />
          )}
        </SummaryCard>
      </div>

      <section className="rounded-xl border border-border bg-card p-4 sm:p-6" aria-labelledby="attention-title">
        <h2 id="attention-title" className="text-base font-semibold text-foreground">
          {t('attentionTitle')}
        </h2>
        {attentionItems.length > 0 ? (
          <ul className="mt-3 space-y-2">
            {attentionItems.map((item) => (
              <li key={item.key} className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                <AlertTriangle aria-hidden="true" className="size-4 shrink-0" />
                {item.label}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 aria-hidden="true" className="size-4 shrink-0" />
            {t('attentionAllGood')}
          </p>
        )}
      </section>
    </div>
  );
}

function SummaryCard({
  title,
  href,
  cta,
  children,
}: {
  title: string;
  href: string;
  cta: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col rounded-xl border border-border bg-card p-4 sm:p-6" aria-label={title}>
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <div className="mt-4 flex-1">{children}</div>
      <Link
        href={href}
        className="mt-4 inline-flex items-center gap-1.5 self-start text-sm font-medium text-primary hover:underline"
      >
        {cta}
        <ArrowRight aria-hidden="true" className="size-4" />
      </Link>
    </section>
  );
}

function MetricGrid({ items }: { items: { label: string; value: string | number }[] }) {
  return (
    <dl className="grid grid-cols-2 gap-4">
      {items.map((item) => (
        <div key={item.label}>
          <dt className="text-xs text-muted-foreground">{item.label}</dt>
          <dd className="text-xl font-semibold text-foreground">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ErrorNote({ message }: { message: string }) {
  return <div className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">{message}</div>;
}
