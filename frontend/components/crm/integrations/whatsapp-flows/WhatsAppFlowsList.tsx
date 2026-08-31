'use client';

import { useMemo, useState, useTransition } from 'react';
import Link from 'next/link';
import { Copy, Plus, RefreshCw, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { cloneWhatsAppFlowAction, syncWhatsAppFlowStatusAction } from '@/app/[locale]/crm/settings/integrations/whatsapp/flows/actions';
import { Button } from '@/components/ui/button';
import type { WhatsAppFlow } from '@/types/whatsapp-flows';

type Props = { locale: string; flows: WhatsAppFlow[]; canEdit: boolean; configured: boolean };

const badgeStyles: Record<WhatsAppFlow['status'], string> = {
  draft: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
  synced: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-200',
  published: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200',
  deprecated: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
  error: 'bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-200',
};

export function WhatsAppFlowsList({ locale, flows, canEdit, configured }: Props) {
  const t = useTranslations('crm.integrationsCatalog.whatsapp.flows');
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const base = `/${locale}/crm/settings/integrations/whatsapp/flows`;
  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    return value ? flows.filter((flow) => `${flow.name} ${flow.flow_key}`.toLowerCase().includes(value)) : flows;
  }, [flows, query]);

  const run = (action: () => Promise<{ ok: boolean; detail?: string }>, success: string) => {
    setMessage(null);
    startTransition(async () => {
      const result = await action();
      setMessage(result.ok ? success : result.detail || t('errors.generic'));
      if (result.ok) router.refresh();
    });
  };
  const clone = (flowId: string) => {
    setMessage(null);
    startTransition(async () => {
      const result = await cloneWhatsAppFlowAction(flowId);
      if (!result.ok) return setMessage(result.detail || t('errors.generic'));
      router.push(`${base}/${result.data.id}`);
    });
  };

  if (!configured) {
    return <div className="rounded-2xl border border-amber-300/60 bg-amber-50 p-8 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100"><h2 className="text-lg font-semibold">{t('notConfigured.title')}</h2><p className="mt-2 text-sm">{t('notConfigured.description')}</p><Button asChild className="mt-5"><Link href={`/${locale}/crm/settings/integrations/whatsapp/account`}>{t('notConfigured.cta')}</Link></Button></div>;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <label className="relative block max-w-md flex-1"><span className="sr-only">{t('search')}</span><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('search')} className="h-10 w-full rounded-lg border border-input bg-background pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring" /></label>
        {canEdit ? <Button asChild><Link href={`${base}/new`}><Plus className="mr-2 size-4" />{t('create')}</Link></Button> : null}
      </div>
      {message ? <p role="status" className="rounded-lg border border-border bg-muted/40 p-3 text-sm">{message}</p> : null}
      {filtered.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-emerald-300 bg-emerald-50/40 px-6 py-14 text-center dark:bg-emerald-950/10"><h2 className="text-lg font-semibold">{query ? t('emptySearch') : t('empty.title')}</h2>{!query ? <><p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">{t('empty.description')}</p>{canEdit ? <Button asChild className="mt-5"><Link href={`${base}/new`}>{t('create')}</Link></Button> : null}</> : null}</div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {filtered.map((flow) => (
            <article key={flow.id} className="group rounded-2xl border border-border bg-card p-5 shadow-xs transition hover:border-emerald-500/30 hover:shadow-sm">
              <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-600 dark:text-emerald-300">{flow.categories.join(' · ')}</p><h2 className="mt-2 text-lg font-semibold text-foreground">{flow.name}</h2><p className="mt-1 font-mono text-xs text-muted-foreground">{flow.flow_key} · v{flow.version}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${badgeStyles[flow.status]}`}>{t(`statuses.${flow.status}`)}</span></div>
              <dl className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><dt className="text-muted-foreground">{t('source')}</dt><dd className="mt-1 font-medium">{t(`sources.${flow.source_mode}`)}</dd></div><div><dt className="text-muted-foreground">{t('metaStatus')}</dt><dd className="mt-1 font-medium">{flow.meta_status || '—'}</dd></div><div className="col-span-2"><dt className="text-muted-foreground">{t('lastSync')}</dt><dd className="mt-1 font-medium">{flow.last_synced_at ? new Date(flow.last_synced_at).toLocaleString(locale) : '—'}</dd></div></dl>
              <div className="mt-5 flex flex-wrap gap-2"><Button asChild size="sm" variant="outline"><Link href={`${base}/${flow.id}`}>{flow.status === 'published' ? t('view') : t('edit')}</Link></Button>{canEdit && flow.provider_flow_id ? <Button size="sm" variant="ghost" disabled={pending} onClick={() => run(() => syncWhatsAppFlowStatusAction(flow.id), t('synced'))}><RefreshCw className="mr-1.5 size-3.5" />{t('syncStatus')}</Button> : null}{canEdit && flow.status === 'published' ? <Button size="sm" variant="ghost" disabled={pending} onClick={() => clone(flow.id)}><Copy className="mr-1.5 size-3.5" />{t('newVersion')}</Button> : null}</div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
