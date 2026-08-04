'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Pencil, Plus, UserRoundCheck, UsersRound } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  createNotificationRecipientAction,
  updateNotificationRecipientAction,
} from '@/app/[locale]/crm/settings/notifications/actions';
import type {
  NotificationRecipientCreateRequest,
  NotificationRecipientItem,
} from '@/types/notifications';

type Props = {
  canEdit: boolean;
  initialRecipients: NotificationRecipientItem[];
};

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const TABLE_WRAP_CLASS = 'hidden';
const TABLE_HEAD_CLASS = 'bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground';
const TABLE_ROW_CLASS = 'transition-colors hover:bg-muted/30';
const KNOWN_RECIPIENT_ERROR_CODES = new Set(['duplicate_recipient', 'invalid_destination']);

export function RecipientsPanel({ canEdit, initialRecipients }: Props) {
  const t = useTranslations('crm.notifications.recipients');
  const [recipients, setRecipients] = useState(initialRecipients);
  const [editing, setEditing] = useState<NotificationRecipientItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toggleErrorId, setToggleErrorId] = useState<string | null>(null);
  const activeRecipients = recipients.filter((recipient) => recipient.status === 'active').length;

  const drawerOpen = creating || editing !== null;
  const closeDrawer = () => {
    setCreating(false);
    setEditing(null);
  };

  const handleSaved = (recipient: NotificationRecipientItem) => {
    setRecipients((current) => {
      const exists = current.some((item) => item.id === recipient.id);
      return exists ? current.map((item) => (item.id === recipient.id ? recipient : item)) : [...current, recipient];
    });
    closeDrawer();
  };

  const toggleStatus = async (recipient: NotificationRecipientItem) => {
    setBusyId(recipient.id);
    setToggleErrorId(null);
    const nextStatus = recipient.status === 'active' ? 'inactive' : 'active';
    const result = await updateNotificationRecipientAction(recipient.id, { status: nextStatus });
    setBusyId(null);
    if (!result.ok) {
      setToggleErrorId(recipient.id);
      return;
    }
    setRecipients((current) => current.map((item) => (item.id === recipient.id ? result.data : item)));
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-lg border border-border bg-card shadow-xs">
        <div className="flex flex-col gap-4 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="grid gap-2 sm:grid-cols-2">
            <RecipientCountBadge icon={UserRoundCheck} label={t('status.active')} value={activeRecipients} tone="success" />
            <RecipientCountBadge icon={UsersRound} label={t('status.inactive')} value={recipients.length - activeRecipients} />
          </div>
          {canEdit && (
            <Button type="button" className="gap-2 self-start sm:self-auto" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden="true" />
              {t('new')}
            </Button>
          )}
        </div>

        {recipients.length === 0 ? (
          <div className="m-4 rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center text-sm text-muted-foreground">
            {t('empty')}
          </div>
        ) : (
          <div className="p-4">
            <div className={TABLE_WRAP_CLASS}>
            <table className="w-full text-left text-sm">
              <thead className={TABLE_HEAD_CLASS}>
                <tr>
                  <th className="px-4 py-3 font-medium">{t('columns.name')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.group')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.channel')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.destination')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.status')}</th>
                  {canEdit && <th className="px-4 py-3 font-medium">{t('columns.actions')}</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {recipients.map((recipient) => (
                  <tr key={recipient.id} className={TABLE_ROW_CLASS}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-foreground">{recipient.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{recipient.group_key}</p>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.group_key}</td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.channel}</td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.destination_masked}</td>
                    <td className="px-4 py-3">
                      <RecipientStatusBadge status={recipient.status} />
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-2">
                            <Button type="button" variant="outline" size="sm" onClick={() => setEditing(recipient)}>
                              <Pencil className="size-3.5" aria-hidden="true" />
                              <span className="sr-only sm:not-sr-only sm:ml-1.5">{t('actions.edit')}</span>
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={busyId === recipient.id}
                              onClick={() => toggleStatus(recipient)}
                            >
                              {busyId === recipient.id && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                              {recipient.status === 'active' ? t('actions.deactivate') : t('actions.activate')}
                            </Button>
                          </div>
                          {toggleErrorId === recipient.id && (
                            <p role="alert" className="text-xs text-destructive">
                              {t('actions.toggleError')}
                            </p>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="grid gap-3 lg:grid-cols-2">
            {recipients.map((recipient) => (
              <li key={recipient.id} className="min-w-0 rounded-lg border border-border bg-background p-4 shadow-xs transition-colors hover:border-primary/25">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-foreground">{recipient.name}</p>
                    <p className="mt-1 truncate text-xs text-muted-foreground">{recipient.destination_masked}</p>
                  </div>
                  <RecipientStatusBadge status={recipient.status} />
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 border-y border-border py-3 text-xs text-muted-foreground">
                  <dt>{t('columns.group')}</dt>
                  <dd className="truncate text-right font-medium text-foreground">{recipient.group_key}</dd>
                  <dt>{t('columns.channel')}</dt>
                  <dd className="text-right font-medium capitalize text-foreground">{recipient.channel}</dd>
                  <dt>{t('columns.destination')}</dt>
                  <dd className="truncate text-right font-medium text-foreground">{recipient.destination_masked}</dd>
                </dl>
                {canEdit && (
                  <div className="mt-3 flex flex-col gap-2">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => setEditing(recipient)}>
                        <Pencil className="size-3.5" aria-hidden="true" />
                        {t('actions.edit')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        disabled={busyId === recipient.id}
                        onClick={() => toggleStatus(recipient)}
                      >
                        {busyId === recipient.id && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                        {recipient.status === 'active' ? t('actions.deactivate') : t('actions.activate')}
                      </Button>
                    </div>
                    {toggleErrorId === recipient.id && (
                      <p role="alert" className="text-xs text-destructive">
                        {t('actions.toggleError')}
                      </p>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          </div>
        )}
      </div>

      {drawerOpen && (
        <RecipientFormDialog recipient={editing} onClose={closeDrawer} onSaved={handleSaved} />
      )}
    </div>
  );
}

function RecipientCountBadge({
  icon: Icon,
  label,
  value,
  tone = 'neutral',
}: {
  icon: typeof UsersRound;
  label: string;
  value: number;
  tone?: 'neutral' | 'success';
}) {
  const styles = {
    neutral: 'border-border bg-background text-muted-foreground',
    success: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  };

  return (
    <div className={`flex min-h-12 items-center gap-3 rounded-md border px-3 py-2 ${styles[tone]}`}>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="text-base font-semibold leading-none text-foreground">{value}</p>
        <p className="mt-1 text-xs">{label}</p>
      </div>
    </div>
  );
}

function RecipientStatusBadge({ status }: { status: 'active' | 'inactive' }) {
  const t = useTranslations('crm.notifications.recipients.status');
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        status === 'active'
          ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'border-border bg-muted text-muted-foreground'
      }`}
    >
      {t(status)}
    </span>
  );
}

function RecipientFormDialog({
  recipient,
  onClose,
  onSaved,
}: {
  recipient: NotificationRecipientItem | null;
  onClose: () => void;
  onSaved: (recipient: NotificationRecipientItem) => void;
}) {
  const t = useTranslations('crm.notifications.recipients.form');
  const statusT = useTranslations('crm.notifications.recipients.status');
  const [groupKey, setGroupKey] = useState(recipient?.group_key ?? '');
  const [name, setName] = useState(recipient?.name ?? '');
  const [destination, setDestination] = useState('');
  const [status, setStatus] = useState<'active' | 'inactive'>(recipient?.status ?? 'active');
  const [busy, setBusy] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setErrorCode(null);

    const result = recipient
      ? await updateNotificationRecipientAction(recipient.id, {
          group_key: groupKey,
          name,
          status,
          ...(destination ? { destination } : {}),
        })
      : await createNotificationRecipientAction({
          group_key: groupKey,
          name,
          destination,
          status,
          channel: 'whatsapp',
        } as NotificationRecipientCreateRequest);

    setBusy(false);
    if (!result.ok) {
      setErrorCode(result.detail);
      return;
    }
    onSaved(result.data);
  };

  const errorMessageKey = errorCode && KNOWN_RECIPIENT_ERROR_CODES.has(errorCode) ? errorCode : 'generic';

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-lg grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-h-[calc(100dvh-2rem)] sm:w-full">
        <DialogHeader className="border-b border-border bg-muted/30 p-4 pr-12 sm:p-5 sm:pr-12">
          <div className="mb-2 flex size-10 items-center justify-center rounded-md border border-border bg-background text-muted-foreground">
            <UsersRound className="size-5" aria-hidden="true" />
          </div>
          <DialogTitle>{recipient ? t('editTitle') : t('createTitle')}</DialogTitle>
          <DialogDescription>{t('destination')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="min-h-0 space-y-4 overflow-y-auto overscroll-contain p-4 sm:p-5">
          {errorCode && (
            <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {t(`errors.${errorMessageKey}`)}
            </p>
          )}

          <label className="space-y-1 text-sm">
            <span className="font-medium text-foreground">{t('name')}</span>
            <input
              className={FIELD_CLASS}
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={160}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-medium text-foreground">{t('group')}</span>
            <input
              className={FIELD_CLASS}
              value={groupKey}
              onChange={(event) => setGroupKey(event.target.value)}
              required
              maxLength={80}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-medium text-foreground">{t('destination')}</span>
            <input
              className={FIELD_CLASS}
              value={destination}
              onChange={(event) => setDestination(event.target.value)}
              placeholder={recipient ? recipient.destination_masked : '+573001112233'}
              required={!recipient}
              minLength={8}
              maxLength={32}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span className="font-medium text-foreground">{t('status')}</span>
            <select
              className={FIELD_CLASS}
              value={status}
              onChange={(event) => setStatus(event.target.value as 'active' | 'inactive')}
            >
              <option value="active">{statusT('active')}</option>
              <option value="inactive">{statusT('inactive')}</option>
            </select>
          </label>

          <DialogFooter className="sticky bottom-0 z-10 -mx-4 -mb-4 border-t border-border bg-background px-4 py-4 shadow-[0_-8px_16px_-16px_rgba(0,0,0,0.35)] sm:-mx-5 sm:-mb-5 sm:px-5">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
              {t('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
