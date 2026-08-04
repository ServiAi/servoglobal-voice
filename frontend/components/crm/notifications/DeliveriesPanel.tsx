'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { CalendarRange, Loader2, Search } from 'lucide-react';

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  fetchNotificationDeliveriesAction,
  fetchNotificationDeliveryAction,
} from '@/app/[locale]/crm/settings/notifications/actions';
import type {
  NotificationCatalogResponse,
  NotificationDeliveryItem,
  NotificationDeliveryListResponse,
  NotificationDeliveryStatus,
  NotificationRuleItem,
} from '@/types/notifications';
import { NotificationStatusBadge } from './NotificationStatusBadge';
import { toLocalDayEndIso, toLocalDayStartIso } from '@/lib/notifications/date-range';

const STATUSES: NotificationDeliveryStatus[] = [
  'pending',
  'processing',
  'sent',
  'delivered',
  'read',
  'failed',
  'skipped',
  'cancelled',
  'dead_letter',
  'manual_review',
];

type Props = {
  initialDeliveries: NotificationDeliveryListResponse | null;
  rules: NotificationRuleItem[];
  catalog: NotificationCatalogResponse | null;
};

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const TABLE_WRAP_CLASS = 'hidden';
const TABLE_HEAD_CLASS = 'bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground';

export function DeliveriesPanel({ initialDeliveries, rules, catalog }: Props) {
  const t = useTranslations('crm.notifications.deliveries');
  const [listing, setListing] = useState(initialDeliveries);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<NotificationDeliveryItem | null>(null);
  const [detailError, setDetailError] = useState(false);
  const emptyFilters = {
    status_filter: '',
    event_type: '',
    rule_id: '',
    date_from: '',
    date_to: '',
  };
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);

  const applyFilters = async (nextFilters: typeof filters, page = 1) => {
    setLoading(true);
    setLoadError(false);
    const result = await fetchNotificationDeliveriesAction({
      page,
      page_size: listing?.page_size ?? 25,
      status_filter: nextFilters.status_filter || undefined,
      event_type: nextFilters.event_type || undefined,
      rule_id: nextFilters.rule_id || undefined,
      date_from: nextFilters.date_from ? toLocalDayStartIso(nextFilters.date_from) : undefined,
      date_to: nextFilters.date_to ? toLocalDayEndIso(nextFilters.date_to) : undefined,
    });
    setLoading(false);
    if (!result.ok) {
      setLoadError(true);
      return;
    }
    setListing(result.data);
  };

  const updateFilter = (key: keyof typeof filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const submitFilters = () => {
    setAppliedFilters(filters);
    applyFilters(filters);
  };

  const changePage = (page: number) => applyFilters(appliedFilters, page);

  const openDetail = async (item: NotificationDeliveryItem) => {
    setSelected(item);
    setDetailError(false);
    const result = await fetchNotificationDeliveryAction(item.id);
    if (result.ok) {
      setSelected(result.data);
    } else {
      setDetailError(true);
    }
  };

  const items = listing?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-lg border border-border bg-card p-4 shadow-xs">
        <div className="mb-4 flex items-center gap-2 text-sm font-medium text-foreground">
          <CalendarRange className="size-4 text-muted-foreground" aria-hidden="true" />
          {t('filters.apply')}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="space-y-1 text-sm">
          <span className="text-xs text-muted-foreground">{t('filters.status')}</span>
          <select
            className={FIELD_CLASS}
            value={filters.status_filter}
            onChange={(event) => updateFilter('status_filter', event.target.value)}
          >
            <option value="">{t('filters.allStatuses')}</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {t(`status.${status}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-xs text-muted-foreground">{t('filters.eventType')}</span>
          <select
            className={FIELD_CLASS}
            value={filters.event_type}
            onChange={(event) => updateFilter('event_type', event.target.value)}
          >
            <option value="">{t('filters.allEvents')}</option>
            {catalog?.event_types.map((event) => (
              <option key={event} value={event}>
                {event}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-xs text-muted-foreground">{t('filters.rule')}</span>
          <select
            className={FIELD_CLASS}
            value={filters.rule_id}
            onChange={(event) => updateFilter('rule_id', event.target.value)}
          >
            <option value="">{t('filters.allRules')}</option>
            {rules.map((rule) => (
              <option key={rule.id} value={rule.id}>
                {rule.name}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-xs text-muted-foreground">{t('filters.dateFrom')}</span>
          <input
            type="date"
            className={FIELD_CLASS}
            value={filters.date_from}
            onChange={(event) => updateFilter('date_from', event.target.value)}
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-xs text-muted-foreground">{t('filters.dateTo')}</span>
          <input
            type="date"
            className={FIELD_CLASS}
            value={filters.date_to}
            onChange={(event) => updateFilter('date_to', event.target.value)}
          />
        </label>
      </div>

        <div className="mt-4 flex justify-end">
          <Button type="button" variant="outline" size="sm" disabled={loading} onClick={submitFilters} className="gap-2">
            <Search className="size-3.5" aria-hidden="true" />
            {loading && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
            {t('filters.apply')}
          </Button>
        </div>
      </div>

      {loadError && (
        <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {t('filters.error')}
        </p>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          {t('loading') || '...'}
        </div>
      )}

      {!loading && items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center text-sm text-muted-foreground">
          {t('empty')}
        </div>
      ) : (
        <>
          <div className={TABLE_WRAP_CLASS}>
            <table className="w-full text-left text-sm">
              <thead className={TABLE_HEAD_CLASS}>
                <tr>
                  <th className="px-4 py-3 font-medium">{t('columns.date')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.rule')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.event')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.recipient')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.scheduledFor')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.attempts')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.status')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    tabIndex={0}
                    role="button"
                    onClick={() => openDetail(item)}
                    onKeyDown={(event) => (event.key === 'Enter' || event.key === ' ') && openDetail(item)}
                    className="cursor-pointer transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <td className="px-4 py-3 text-muted-foreground">{new Date(item.created_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-foreground">{item.rule_name ?? '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{item.event_type ?? '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{item.recipient_masked}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(item.scheduled_for).toLocaleString()}</td>
                    <td className="px-4 py-3 text-muted-foreground">{item.attempts}</td>
                    <td className="px-4 py-3">
                      <NotificationStatusBadge status={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="grid gap-3 lg:grid-cols-2">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => openDetail(item)}
                  className="w-full rounded-lg border border-border bg-card p-4 text-left shadow-xs transition-colors hover:border-primary/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-foreground">{item.rule_name ?? '—'}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</p>
                    </div>
                    <NotificationStatusBadge status={item.status} />
                  </div>
                  <dl className="mt-4 grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-3 gap-y-2 border-y border-border py-3 text-xs text-muted-foreground">
                    <dt>{t('columns.event')}</dt>
                    <dd className="truncate text-right font-medium text-foreground">{item.event_type ?? '—'}</dd>
                    <dt>{t('columns.recipient')}</dt>
                    <dd className="truncate text-right font-medium text-foreground">{item.recipient_masked}</dd>
                    <dt>{t('columns.scheduledFor')}</dt>
                    <dd className="text-right font-medium text-foreground">{new Date(item.scheduled_for).toLocaleString()}</dd>
                    <dt>{t('columns.attempts')}</dt>
                    <dd className="text-right font-medium text-foreground">{item.attempts}</dd>
                  </dl>
                </button>
              </li>
            ))}
          </ul>

          {listing && listing.pages > 1 && (
            <div className="flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {listing.page} / {listing.pages}
              </span>
              <div className="flex gap-2">
                <Button type="button" variant="outline" size="sm" disabled={listing.page <= 1} onClick={() => changePage(listing.page - 1)}>
                  ‹
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={listing.page >= listing.pages}
                  onClick={() => changePage(listing.page + 1)}
                >
                  ›
                </Button>
              </div>
            </div>
          )}
        </>
      )}

      {selected && (
        <DeliveryDetailDialog delivery={selected} staleData={detailError} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function DeliveryDetailDialog({
  delivery,
  staleData,
  onClose,
}: {
  delivery: NotificationDeliveryItem;
  staleData: boolean;
  onClose: () => void;
}) {
  const t = useTranslations('crm.notifications.deliveries.detail');

  const timeline = [
    { key: 'created', at: delivery.created_at },
    { key: 'sent', at: delivery.sent_at },
    { key: 'delivered', at: delivery.delivered_at },
    { key: 'read', at: delivery.read_at },
    { key: 'failed', at: delivery.failed_at },
  ].filter((entry) => entry.at) as { key: string; at: string }[];

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-2xl grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-h-[calc(100dvh-2rem)] sm:w-full">
        <DialogHeader className="border-b border-border bg-muted/30 p-4 pr-12 sm:p-5 sm:pr-12">
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{delivery.recipient_masked}</DialogDescription>
        </DialogHeader>
        <div className="min-h-0 space-y-5 overflow-y-auto overscroll-contain p-4 sm:p-5">
        {staleData && (
          <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {t('staleData')}
          </p>
        )}
        <dl className="grid grid-cols-1 gap-3 rounded-lg border border-border bg-card p-4 text-sm sm:grid-cols-2">
          <dt className="text-muted-foreground">{t('status')}</dt>
          <dd>
            <NotificationStatusBadge status={delivery.status} />
          </dd>
          <dt className="text-muted-foreground">{t('rule')}</dt>
          <dd className="text-foreground">{delivery.rule_name ?? '—'}</dd>
          <dt className="text-muted-foreground">{t('event')}</dt>
          <dd className="text-foreground">{delivery.event_type ?? '—'}</dd>
          <dt className="text-muted-foreground">{t('template')}</dt>
          <dd className="text-foreground">{delivery.template_key ?? '—'}</dd>
          <dt className="text-muted-foreground">{t('recipient')}</dt>
          <dd className="text-foreground">{delivery.recipient_masked}</dd>
          <dt className="text-muted-foreground">{t('scheduledFor')}</dt>
          <dd className="text-foreground">{new Date(delivery.scheduled_for).toLocaleString()}</dd>
          <dt className="text-muted-foreground">{t('attempts')}</dt>
          <dd className="text-foreground">{delivery.attempts}</dd>
          {delivery.provider_message_id && (
            <>
              <dt className="text-muted-foreground">{t('providerMessageId')}</dt>
              <dd className="break-all text-foreground">{delivery.provider_message_id}</dd>
            </>
          )}
          {delivery.error_code && (
            <>
              <dt className="text-muted-foreground">{t('errorCode')}</dt>
              <dd className="text-destructive">{delivery.error_code}</dd>
            </>
          )}
        </dl>

        {timeline.length > 0 && (
          <div className="space-y-3 rounded-lg border border-border bg-muted/20 p-4">
            <p className="text-sm font-medium text-foreground">{t('timeline')}</p>
            <ol className="space-y-1.5 text-sm text-muted-foreground">
              {timeline.map((entry) => (
                <li key={entry.key} className="flex items-center justify-between gap-3 rounded-md bg-background px-3 py-2">
                  <span>{t(`timelineEvents.${entry.key}`)}</span>
                  <span>{new Date(entry.at).toLocaleString()}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
