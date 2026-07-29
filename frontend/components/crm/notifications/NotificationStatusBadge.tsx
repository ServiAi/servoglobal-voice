'use client';

import { useTranslations } from 'next-intl';
import type { NotificationDeliveryStatus } from '@/types/notifications';

const styles: Record<NotificationDeliveryStatus, string> = {
  pending: 'border-border bg-muted text-muted-foreground',
  processing: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  sent: 'border-sky-500/25 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  delivered: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  read: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  failed: 'border-destructive/25 bg-destructive/10 text-destructive',
  skipped: 'border-border bg-muted text-muted-foreground',
  cancelled: 'border-border bg-muted text-muted-foreground',
  dead_letter: 'border-destructive/25 bg-destructive/10 text-destructive',
  manual_review: 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300',
};

export function NotificationStatusBadge({ status }: { status: NotificationDeliveryStatus }) {
  const t = useTranslations('crm.notifications.deliveries.status');
  return (
    <span className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}>
      <span aria-hidden="true" className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" />
      {t(status)}
    </span>
  );
}
