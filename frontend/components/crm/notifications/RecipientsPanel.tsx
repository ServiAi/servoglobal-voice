'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Pencil, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { createNotificationRecipient, updateNotificationRecipient } from '@/lib/api/notification-admin';
import type {
  NotificationRecipientCreateRequest,
  NotificationRecipientItem,
} from '@/types/notifications';

type Props = {
  accessToken: string;
  canEdit: boolean;
  initialRecipients: NotificationRecipientItem[];
};

const KNOWN_RECIPIENT_ERROR_CODES = new Set(['duplicate_recipient', 'invalid_destination']);

export function RecipientsPanel({ accessToken, canEdit, initialRecipients }: Props) {
  const t = useTranslations('crm.notifications.recipients');
  const [recipients, setRecipients] = useState(initialRecipients);
  const [editing, setEditing] = useState<NotificationRecipientItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

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
    const nextStatus = recipient.status === 'active' ? 'inactive' : 'active';
    const result = await updateNotificationRecipient(accessToken, recipient.id, { status: nextStatus });
    setBusyId(null);
    if (result.ok) {
      setRecipients((current) => current.map((item) => (item.id === recipient.id ? result.data : item)));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <div className="flex justify-end">
          <Button type="button" className="gap-2" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            {t('new')}
          </Button>
        </div>
      )}

      {recipients.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          {t('empty')}
        </div>
      ) : (
        <>
          <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
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
                  <tr key={recipient.id}>
                    <td className="px-4 py-3 font-medium text-foreground">{recipient.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.group_key}</td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.channel}</td>
                    <td className="px-4 py-3 text-muted-foreground">{recipient.destination_masked}</td>
                    <td className="px-4 py-3">
                      <RecipientStatusBadge status={recipient.status} />
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3">
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
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="flex flex-col gap-3 md:hidden">
            {recipients.map((recipient) => (
              <li key={recipient.id} className="rounded-xl border border-border bg-card p-4 shadow-xs">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-foreground">{recipient.name}</p>
                  <RecipientStatusBadge status={recipient.status} />
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <dt>{t('columns.group')}</dt>
                  <dd className="text-right">{recipient.group_key}</dd>
                  <dt>{t('columns.destination')}</dt>
                  <dd className="text-right">{recipient.destination_masked}</dd>
                </dl>
                {canEdit && (
                  <div className="mt-3 flex gap-2">
                    <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => setEditing(recipient)}>
                      {t('actions.edit')}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      disabled={busyId === recipient.id}
                      onClick={() => toggleStatus(recipient)}
                    >
                      {recipient.status === 'active' ? t('actions.deactivate') : t('actions.activate')}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {drawerOpen && (
        <RecipientFormDialog accessToken={accessToken} recipient={editing} onClose={closeDrawer} onSaved={handleSaved} />
      )}
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
  accessToken,
  recipient,
  onClose,
  onSaved,
}: {
  accessToken: string;
  recipient: NotificationRecipientItem | null;
  onClose: () => void;
  onSaved: (recipient: NotificationRecipientItem) => void;
}) {
  const t = useTranslations('crm.notifications.recipients.form');
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
      ? await updateNotificationRecipient(accessToken, recipient.id, {
          group_key: groupKey,
          name,
          status,
          ...(destination ? { destination } : {}),
        })
      : await createNotificationRecipient(accessToken, {
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
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{recipient ? t('editTitle') : t('createTitle')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {errorCode && (
            <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {t(`errors.${errorMessageKey}`)}
            </p>
          )}

          <label className="space-y-1 text-sm">
            <span>{t('name')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={160}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span>{t('group')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={groupKey}
              onChange={(event) => setGroupKey(event.target.value)}
              required
              maxLength={80}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span>{t('destination')}</span>
            <input
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={destination}
              onChange={(event) => setDestination(event.target.value)}
              placeholder={recipient ? recipient.destination_masked : '+573001112233'}
              required={!recipient}
              minLength={8}
              maxLength={32}
            />
          </label>

          <label className="space-y-1 text-sm">
            <span>{t('status')}</span>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={status}
              onChange={(event) => setStatus(event.target.value as 'active' | 'inactive')}
            >
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
          </label>

          <DialogFooter>
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
