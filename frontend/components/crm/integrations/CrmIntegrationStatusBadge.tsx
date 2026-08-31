'use client';

import { useTranslations } from 'next-intl';
import type { IntegrationStatus } from '@/types/crm';

const styles: Record<IntegrationStatus, string> = {
  active: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  configured: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  error: 'border-destructive/25 bg-destructive/10 text-destructive',
  not_configured: 'border-border bg-muted text-muted-foreground',
};

export function CrmIntegrationStatusBadge({ status }: { status: IntegrationStatus }) {
  const t = useTranslations('crm.integrationStatus');
  const labelKey = status === 'not_configured' ? 'notConfigured' : status;
  return (
    <span className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}>
      <span aria-hidden="true" className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" />
      {t(labelKey)}
    </span>
  );
}
