'use client';

import { useMemo, useState } from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { integrationCatalog, integrationCategories } from '@/lib/integrations/catalog';
import type { IntegrationCatalogStatusResponse, IntegrationProvider, IntegrationStatus } from '@/types/crm';
import { IntegrationCatalogCard } from './IntegrationCatalogCard';

type StatusFilter = 'all' | 'connected' | 'not_configured' | 'error';
type Props = {
  locale: string;
  enabledProviders: IntegrationProvider[];
  statuses: IntegrationCatalogStatusResponse[];
  loadError: boolean;
};

const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();

export function IntegrationCatalog({ locale, enabledProviders, statuses, loadError }: Props) {
  const t = useTranslations('crm.integrationsCatalog');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const enabled = useMemo(() => new Set(enabledProviders), [enabledProviders]);
  const statusByProvider = useMemo(() => new Map(statuses.map((item) => [item.provider, item.status])), [statuses]);
  const normalizedQuery = normalize(query.trim());
  const items = integrationCatalog.filter((item) => {
    if (!enabled.has(item.provider)) return false;
    const status = statusByProvider.get(item.provider) ?? (loadError ? 'error' : 'not_configured');
    const matchesStatus = statusFilter === 'all'
      || (statusFilter === 'connected' && (status === 'active' || status === 'configured'))
      || statusFilter === status;
    if (!matchesStatus) return false;
    if (!normalizedQuery) return true;
    return [t(`providers.${item.provider}.name`), t(`providers.${item.provider}.description`), t(`categories.${item.category}`)]
      .some((value) => normalize(value).includes(normalizedQuery));
  });
  const filters: StatusFilter[] = ['all', 'connected', 'not_configured', 'error'];

  return (
    <div className="space-y-7">
      <section className="rounded-xl border border-border bg-card/70 p-4 shadow-xs" aria-label={t('controlsLabel')}>
        <div className="grid gap-4 lg:grid-cols-[minmax(16rem,1fr)_auto] lg:items-center">
          <label className="relative block">
            <span className="sr-only">{t('searchLabel')}</span>
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t('searchPlaceholder')} className="min-h-11 w-full rounded-lg border border-border bg-background pl-10 pr-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-primary/60 focus:ring-2 focus:ring-primary/15" />
          </label>
          <div className="flex flex-wrap items-center gap-2" aria-label={t('filtersLabel')}>
            <SlidersHorizontal className="mr-1 size-4 text-muted-foreground" aria-hidden="true" />
            {filters.map((filter) => (
              <button key={filter} type="button" aria-pressed={statusFilter === filter} onClick={() => setStatusFilter(filter)} className={`min-h-9 rounded-full border px-3 text-sm font-medium outline-none transition focus-visible:ring-2 focus-visible:ring-ring ${statusFilter === filter ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background text-muted-foreground hover:border-primary/30 hover:text-foreground'}`}>
                {t(`filters.${filter === 'not_configured' ? 'notConfigured' : filter}`)}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-3 text-xs text-muted-foreground" aria-live="polite">{t('results', { count: items.length })}</p>
      </section>

      {loadError ? <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">{t('loadError')}</div> : null}

      {items.length ? integrationCategories.map((category) => {
        const categoryItems = items.filter((item) => item.category === category);
        if (!categoryItems.length) return null;
        return (
          <section key={category} aria-labelledby={`integration-category-${category}`} className="space-y-4">
            <div className="flex items-center gap-3 border-b border-border pb-3">
              <h2 id={`integration-category-${category}`} className="text-lg font-semibold text-foreground">{t(`categories.${category}`)}</h2>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground">{categoryItems.length}</span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {categoryItems.map((item) => {
                const status = (statusByProvider.get(item.provider) ?? (loadError ? 'error' : 'not_configured')) as IntegrationStatus;
                const action = status === 'error' ? 'review' : status === 'not_configured' ? 'configure' : 'manage';
                return <IntegrationCatalogCard key={item.provider} {...item} locale={locale} name={t(`providers.${item.provider}.name`)} description={t(`providers.${item.provider}.description`)} categoryLabel={t(`categories.${item.category}`)} status={status} actionLabel={t(`actions.${action}`)} />;
              })}
            </div>
          </section>
        );
      }) : (
        <div className="rounded-xl border border-dashed border-border bg-muted/20 px-6 py-14 text-center">
          <h2 className="text-base font-semibold text-foreground">{query.trim() ? t('empty.searchTitle', { query: query.trim() }) : t(`empty.${statusFilter}`)}</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{t('empty.description')}</p>
        </div>
      )}
    </div>
  );
}
