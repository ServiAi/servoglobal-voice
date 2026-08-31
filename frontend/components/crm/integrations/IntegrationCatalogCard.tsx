import Link from 'next/link';
import { ArrowUpRight, CalendarDays, Mail, MessageSquare, Phone } from 'lucide-react';
import type { IntegrationCatalogItem } from '@/lib/integrations/catalog';
import type { IntegrationStatus } from '@/types/crm';
import { CrmIntegrationStatusBadge } from './CrmIntegrationStatusBadge';

const icons = { calendar: CalendarDays, mail: Mail, message: MessageSquare, phone: Phone };
const iconStyles = {
  calendar: 'bg-sky-500/10 text-sky-600 dark:text-sky-300',
  mail: 'bg-amber-500/10 text-amber-600 dark:text-amber-300',
  message: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-300',
  phone: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-300',
};

type Props = IntegrationCatalogItem & {
  locale: string;
  name: string;
  description: string;
  categoryLabel: string;
  status: IntegrationStatus;
  actionLabel: string;
};

export function IntegrationCatalogCard({ locale, name, description, categoryLabel, status, href, icon, actionLabel }: Props) {
  const Icon = icons[icon];
  return (
    <article className="group flex min-h-64 flex-col rounded-xl border border-border bg-card p-5 shadow-xs transition duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md focus-within:border-primary/40 focus-within:ring-2 focus-within:ring-primary/20">
      <div className="flex items-start justify-between gap-4">
        <span className={`inline-flex size-11 items-center justify-center rounded-lg ${iconStyles[icon]}`} aria-hidden="true"><Icon className="size-5" /></span>
        <CrmIntegrationStatusBadge status={status} />
      </div>
      <div className="mt-5 flex-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.15em] text-muted-foreground">{categoryLabel}</p>
        <h3 className="mt-1 text-lg font-semibold text-foreground">{name}</h3>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
      </div>
      <Link
        href={`/${locale}${href}`}
        className="mt-5 inline-flex min-h-10 items-center justify-between gap-3 border-t border-border pt-4 text-sm font-semibold text-foreground outline-none transition hover:text-primary focus-visible:text-primary"
        aria-label={`${actionLabel}: ${name}`}
      >
        {actionLabel}
        <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden="true" />
      </Link>
    </article>
  );
}
