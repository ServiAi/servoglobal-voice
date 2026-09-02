'use client';

import Link from 'next/link';
import { ChevronRight, MessageSquare } from 'lucide-react';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import type { IntegrationStatus } from '@/types/crm';
import { CrmIntegrationStatusBadge } from './CrmIntegrationStatusBadge';

type Props = { locale: string; status: IntegrationStatus; basePath?: string; includeFlows?: boolean };

export function WhatsAppIntegrationNavigation({ locale, status, basePath = '/crm/settings/integrations/whatsapp', includeFlows = true }: Props) {
  const pathname = usePathname();
  const t = useTranslations('crm.integrationsCatalog');
  const base = `/${locale}${basePath}`;
  const links = [
    { key: 'overview', href: base },
    { key: 'account', href: `${base}/account` },
    { key: 'templates', href: `${base}/templates` },
    ...(includeFlows ? [{ key: 'flows' as const, href: `${base}/flows` }] : []),
    { key: 'test', href: `${base}/test` },
  ] as const;
  const isActive = (href: string) => pathname === href || (href !== base && pathname.startsWith(`${href}/`));
  const current = links.find((item) => isActive(item.href)) ?? links[0];

  return (
    <div className="space-y-5">
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground">
        <Link href={base.replace(/\/whatsapp$/, '')} className="rounded-sm outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">{t('title')}</Link>
        <ChevronRight className="size-4" aria-hidden="true" />
        <Link href={base} className="rounded-sm outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">WhatsApp</Link>
        {current.key !== 'overview' ? <><ChevronRight className="size-4" aria-hidden="true" /><span aria-current="page" className="font-medium text-foreground">{t(`whatsapp.navigation.${current.key}`)}</span></> : null}
      </nav>
      <header className="flex flex-col gap-4 border-l-4 border-emerald-500 pl-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex size-11 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-300" aria-hidden="true"><MessageSquare className="size-5" /></span>
          <div>
            <h1 className="text-2xl font-bold text-foreground">WhatsApp</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">{t('providers.whatsapp.description')}</p>
          </div>
        </div>
        <CrmIntegrationStatusBadge status={status} />
      </header>
      <nav aria-label={t('whatsapp.navigationLabel')} className={`grid grid-cols-2 gap-2 rounded-xl border border-border bg-card p-2 ${includeFlows ? 'sm:grid-cols-5' : 'sm:grid-cols-4'}`}>
        {links.map((item) => {
          const active = isActive(item.href);
          return <Link key={item.key} href={item.href} aria-current={active ? 'page' : undefined} className={`flex min-h-10 items-center justify-center rounded-lg px-3 text-center text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring ${active ? 'bg-primary text-primary-foreground shadow-xs' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}>{t(`whatsapp.navigation.${item.key}`)}</Link>;
        })}
      </nav>
    </div>
  );
}
